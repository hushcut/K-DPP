import json
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
import init_data


@contextmanager
def scratch_schema_engine():
    """Engine bound to an empty throwaway PostgreSQL schema (tables and trigger functions included)."""
    schema = f"scratch_{uuid.uuid4().hex[:12]}"
    with database.engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    engine = create_engine(database.SQLALCHEMY_DATABASE_URL,
                           connect_args={"options": f"-c search_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with database.engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")


def test_foreign_keys_are_enforced(client):
    with database.SessionLocal() as session:
        session.add(database.ProfileFactor(profile_id=999, material_id=999,
                                           factor_id=999, selection_assumption="orphan"))
        with pytest.raises(IntegrityError, match='foreign key constraint'):
            session.commit()


def test_import_does_not_connect_to_database():
    env = dict(os.environ, K_DPP_DATABASE_URL='postgresql+psycopg://nobody@127.0.0.1:1/unreachable_test')
    subprocess.run([sys.executable, '-c', 'import database'], env=env,
                   cwd=Path(database.__file__).parent, check=True)


def test_additive_migration_preserves_legacy_data_and_is_repeatable():
    with scratch_schema_engine() as engine:
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


def test_factor_versions_and_snapshot_roundtrip():
    with scratch_schema_engine() as engine:
        database.ensure_schema(engine)
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


def selected_factor(material, key):
    return database.MaterialFactor(factor_key=key, version='1', material_id=material.id,
        value_decimal='1.23', unit='kg CO2eq/kg fiber', method='test',
        scope='fiber_production_estimate', product_form='fiber', production_system='test',
        source_name='fixture', source_url='https://example.invalid', source_locator='test',
        evidence_type='literature', review_status='selected', usage_scope='public_estimate')


def draft_profile(key):
    return database.CalculationProfile(key=key, version='1', status='draft',
        formula_version='fiber_mass_v2', method='test', scope='fiber_production_estimate',
        usage_scope='public_estimate')


def test_unpublished_rows_stay_editable(client):
    # A BEFORE trigger function that returns NULL silently skips the row instead of failing,
    # so read every change back on a fresh session.
    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en='cotton').one()
        candidate = selected_factor(material, 'candidate')
        candidate.review_status = 'candidate'
        profile = draft_profile('draft-edit')
        session.add_all([candidate, profile])
        session.flush()
        session.add(database.ProfileFactor(profile_id=profile.id, material_id=material.id,
            factor_id=candidate.id, selection_assumption='first'))
        session.commit()
        candidate.review_note = 'edited'
        profile.method = 'edited-method'
        session.get(database.ProfileFactor, (profile.id, material.id)).selection_assumption = 'second'
        session.commit()
        ids = {'factor': candidate.id, 'profile': profile.id, 'material': material.id}

    with database.SessionLocal() as session:
        assert session.get(database.MaterialFactor, ids['factor']).review_note == 'edited'
        profile = session.get(database.CalculationProfile, ids['profile'])
        assert profile.method == 'edited-method'
        link = session.get(database.ProfileFactor, (ids['profile'], ids['material']))
        assert link.selection_assumption == 'second'
        session.delete(link)
        session.flush()
        session.delete(profile)
        session.delete(session.get(database.MaterialFactor, ids['factor']))
        session.commit()

    with database.SessionLocal() as session:
        assert session.query(database.ProfileFactor).count() == 0
        assert session.query(database.CalculationProfile).count() == 0
        assert session.query(database.MaterialFactor).count() == 0

    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en='cotton').one()
        factor = selected_factor(material, 'activate')
        profile = draft_profile('activate')
        session.add_all([factor, profile])
        session.flush()
        session.add(database.ProfileFactor(profile_id=profile.id, material_id=material.id,
            factor_id=factor.id, selection_assumption='fixture selection'))
        session.commit()
        profile.status = 'active'
        session.commit()
        profile_id = profile.id
    with database.SessionLocal() as session:
        assert session.get(database.CalculationProfile, profile_id).status == 'active'


@pytest.mark.parametrize(('change', 'message'), [
    ('delete_selected_factor', 'selected material factor is immutable'),
    ('delete_published_profile', 'published calculation profile is immutable'),
    ('add_factor_to_published_profile', 'published profile factors are immutable'),
    ('edit_published_profile_factor', 'published profile factors are immutable'),
    ('activate_second_profile', 'an active calculation profile already exists'),
])
def test_published_policy_rejects_changes(client, change, message):
    with database.SessionLocal() as session:
        cotton = session.query(database.Material).filter_by(name_en='cotton').one()
        polyester = session.query(database.Material).filter_by(name_en='polyester').one()
        factor = selected_factor(cotton, 'published')
        spare = selected_factor(polyester, 'spare')
        profile = draft_profile('published')
        session.add_all([factor, spare, profile])
        session.flush()
        link = database.ProfileFactor(profile_id=profile.id, material_id=cotton.id,
            factor_id=factor.id, selection_assumption='fixture selection')
        session.add(link)
        session.commit()
        profile.status = 'active'
        session.commit()

        if change == 'delete_selected_factor':
            session.delete(spare)
        elif change == 'delete_published_profile':
            session.delete(profile)
        elif change == 'add_factor_to_published_profile':
            session.add(database.ProfileFactor(profile_id=profile.id, material_id=polyester.id,
                factor_id=spare.id, selection_assumption='late addition'))
        elif change == 'edit_published_profile_factor':
            link.selection_assumption = 'changed'
        else:
            second = draft_profile('second')
            session.add(second)
            session.flush()
            session.add(database.ProfileFactor(profile_id=second.id, material_id=cotton.id,
                factor_id=factor.id, selection_assumption='fixture selection'))
            session.commit()
            second.status = 'active'
        with pytest.raises(IntegrityError, match=message):
            session.commit()
        session.rollback()
