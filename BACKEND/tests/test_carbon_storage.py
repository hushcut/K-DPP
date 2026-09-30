import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
import init_data


def test_sqlite_foreign_keys_are_enabled(client):
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    with database.SessionLocal() as session:
        session.add(database.ProfileFactor(profile_id=999, material_id=999,
                                           factor_id=999, selection_assumption="orphan"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_import_does_not_create_database(tmp_path):
    path = tmp_path / 'untouched.db'
    env = dict(os.environ, K_DPP_DATABASE_URL=f'sqlite:///{path.as_posix()}')
    subprocess.run([sys.executable, '-c', 'import database'], env=env,
                   cwd=Path(database.__file__).parent, check=True)
    assert not path.exists()


def test_additive_migration_preserves_legacy_data_and_is_repeatable(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path / "legacy.db").as_posix()}')
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE materials (id INTEGER PRIMARY KEY, name_ko TEXT, '
                                 'name_en TEXT, aliases TEXT, carbon_factor FLOAT, unit TEXT, '
                                 'source TEXT, description TEXT)')
            conn.exec_driver_sql("INSERT INTO materials VALUES (7, '면', 'cotton', '[]', 123.4, "
                                 "'custom', 'preserve source', 'preserve description')")
            conn.exec_driver_sql('CREATE TABLE analysis_results (id INTEGER PRIMARY KEY, '
                                 'materials TEXT, carbon_footprint FLOAT)')
            conn.exec_driver_sql("INSERT INTO analysis_results VALUES (9, '{}', 12.34)")
        database.ensure_schema(engine)
        database.ensure_schema(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT source, description, carbon_factor FROM materials').one() == (
                'preserve source', 'preserve description', 123.4)
            assert conn.exec_driver_sql('SELECT id, carbon_footprint, calculation_snapshot_json '
                                        'FROM analysis_results').one() == (9, 12.34, None)
            assert conn.exec_driver_sql('SELECT count(*) FROM schema_migrations').scalar_one() == 2
        assert {'material_factors', 'calculation_profiles', 'profile_factors'} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_selected_factors_and_published_profiles_are_immutable(client):
    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en='cotton').one()
        factor = database.MaterialFactor(factor_key='immutable', version='1',
            material_id=material.id, value_decimal='1.23', unit='kg CO2eq/kg fiber',
            method='test', scope='fiber_production_estimate', product_form='fiber',
            production_system='test', source_name='fixture', source_url='https://example.invalid',
            source_locator='test', evidence_type='literature', review_status='selected',
            usage_scope='public_estimate')
        profile = database.CalculationProfile(key='immutable', version='1', status='draft',
            formula_version='fiber_mass_v2', method='test', scope='fiber_production_estimate',
            usage_scope='public_estimate')
        session.add_all([factor, profile])
        session.flush()
        link = database.ProfileFactor(profile_id=profile.id, material_id=material.id,
            factor_id=factor.id, selection_assumption='fixture selection')
        session.add(link)
        session.commit()

        profile.status = 'active'
        session.commit()

        factor.value_decimal = '9.99'
        with pytest.raises(IntegrityError, match='selected material factor is immutable'):
            session.commit()
        session.rollback()

        profile.method = 'changed'
        with pytest.raises(IntegrityError, match='published calculation profile is immutable'):
            session.commit()
        session.rollback()

        session.delete(link)
        with pytest.raises(IntegrityError, match='published profile factors are immutable'):
            session.commit()
        session.rollback()

        profile.status = 'retired'
        session.commit()
        assert profile.status == 'retired'


def test_profile_activation_rejects_incomplete_policy(client):
    with database.SessionLocal() as session:
        empty = database.CalculationProfile(key='empty', version='1', status='draft',
            formula_version='fiber_mass_v2', method='test', scope='fiber_production_estimate',
            usage_scope='public_estimate')
        session.add(empty)
        session.commit()
        empty.status = 'active'
        with pytest.raises(IntegrityError, match='factors are incomplete or incompatible'):
            session.commit()
        session.rollback()


def test_seed_preserves_existing_material(client):
    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en='cotton').one()
        material.carbon_factor = 123.4
        material.aliases = '["custom"]'
        session.commit()
    init_data.seed_materials()
    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en='cotton').one()
        assert material.carbon_factor == 123.4
        assert material.aliases == '["custom"]'


def test_factor_versions_and_snapshot_roundtrip(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path / "versions.db").as_posix()}')
    database.ensure_schema(engine)
    try:
        with Session(engine) as session:
            material = database.Material(name_ko='시험', name_en='synthetic_fixture', carbon_factor=1)
            session.add(material)
            session.flush()
            def factor(version):
                return database.MaterialFactor(
                    factor_key='fixture', version=version, material_id=material.id,
                    value_decimal='1.2300', unit='kg CO2eq/kg fiber', method='test', scope='test',
                    product_form='test', production_system='test', source_name='fixture',
                    source_url='https://example.invalid', source_locator='test',
                    evidence_type='placeholder', usage_scope='test')
            session.add_all([factor('1'), factor('2')])
            snapshot = json.dumps({'factors': [{'value': '1.2300', 'version': '1'}]})
            result = database.AnalysisResult(materials='{}', carbon_footprint=1.23,
                snapshot_schema_version=1, calculation_snapshot_json=snapshot)
            session.add(result)
            session.commit()
            assert session.query(database.MaterialFactor).count() == 2
            assert session.get(database.AnalysisResult, result.id).calculation_snapshot_json == snapshot
            session.add(factor('1'))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.query(database.AnalysisResult).one().calculation_snapshot_json == snapshot
    finally:
        engine.dispose()
