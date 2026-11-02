import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

import database


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


def test_factor_versions_and_snapshot_roundtrip(client):
    with database.SessionLocal() as session:
        material = session.query(database.Material).filter_by(name_en="cotton").one()
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


def test_draft_link_cannot_be_moved_into_published_profile(client):
    with database.SessionLocal() as session:
        cotton = session.query(database.Material).filter_by(name_en="cotton").one()
        polyester = session.query(database.Material).filter_by(name_en="polyester").one()
        published = draft_profile("destination")
        draft = draft_profile("source")
        cotton_factor = selected_factor(cotton, "cotton")
        polyester_factor = selected_factor(polyester, "polyester")
        session.add_all([published, draft, cotton_factor, polyester_factor])
        session.flush()
        session.add(database.ProfileFactor(profile_id=published.id, material_id=cotton.id,
            factor_id=cotton_factor.id, selection_assumption="fixture"))
        moving = database.ProfileFactor(profile_id=draft.id, material_id=polyester.id,
            factor_id=polyester_factor.id, selection_assumption="fixture")
        session.add(moving)
        session.commit()
        published.status = "active"
        session.commit()
        moving.profile_id = published.id
        with pytest.raises(IntegrityError, match="published profile factors are immutable"):
            session.commit()
        session.rollback()
