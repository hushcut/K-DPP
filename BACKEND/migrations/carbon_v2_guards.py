# Frozen DDL for the carbon V2 migration; do not import runtime models here.
IMMUTABILITY_TRIGGERS = (
    ("trg_selected_factor_no_update", "BEFORE UPDATE ON material_factors", """
        IF OLD.review_status = 'selected' THEN
            RAISE EXCEPTION 'selected material factor is immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_selected_factor_no_delete", "BEFORE DELETE ON material_factors", """
        IF OLD.review_status = 'selected' THEN
            RAISE EXCEPTION 'selected material factor is immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN OLD;
    """),
    ("trg_profile_insert_as_draft", "BEFORE INSERT ON calculation_profiles", """
        IF NEW.status != 'draft' THEN
            RAISE EXCEPTION 'calculation profile must be created as draft'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_profile_activation_requires_factors", "BEFORE UPDATE OF status ON calculation_profiles", """
        IF OLD.status = 'draft' AND NEW.status = 'active' AND (
            NOT EXISTS (
                SELECT 1 FROM profile_factors pf WHERE pf.profile_id = OLD.id
            ) OR EXISTS (
                SELECT 1
                FROM profile_factors pf
                LEFT JOIN material_factors mf ON mf.id = pf.factor_id
                WHERE pf.profile_id = OLD.id AND (
                    mf.id IS NULL OR mf.material_id != pf.material_id
                    OR mf.review_status != 'selected'
                    OR mf.evidence_type NOT IN ('literature', 'derived')
                    OR mf.unit != 'kg CO2eq/kg fiber'
                    OR mf.method != NEW.method OR mf.scope != NEW.scope
                    OR mf.usage_scope != NEW.usage_scope
                    OR trim(pf.selection_assumption) = ''
                )
            )
        ) THEN
            RAISE EXCEPTION 'calculation profile factors are incomplete or incompatible'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_profile_activation_unique", "BEFORE UPDATE OF status ON calculation_profiles", """
        IF OLD.status = 'draft' AND NEW.status = 'active' AND EXISTS (
            SELECT 1 FROM calculation_profiles other
            WHERE other.id != OLD.id AND other.status = 'active'
              AND other.usage_scope = NEW.usage_scope
        ) THEN
            RAISE EXCEPTION 'an active calculation profile already exists'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_published_profile_no_rewrite", "BEFORE UPDATE ON calculation_profiles", """
        IF OLD.status IN ('active', 'retired') AND NOT (
            OLD.status = 'active' AND NEW.status = 'retired'
            AND NEW.key IS NOT DISTINCT FROM OLD.key
            AND NEW.version IS NOT DISTINCT FROM OLD.version
            AND NEW.formula_version IS NOT DISTINCT FROM OLD.formula_version
            AND NEW.method IS NOT DISTINCT FROM OLD.method
            AND NEW.scope IS NOT DISTINCT FROM OLD.scope
            AND NEW.usage_scope IS NOT DISTINCT FROM OLD.usage_scope
            AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
        ) THEN
            RAISE EXCEPTION 'published calculation profile is immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_published_profile_no_delete", "BEFORE DELETE ON calculation_profiles", """
        IF OLD.status IN ('active', 'retired') THEN
            RAISE EXCEPTION 'published calculation profile is immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN OLD;
    """),
    ("trg_published_profile_factor_no_insert", "BEFORE INSERT ON profile_factors", """
        IF (SELECT status FROM calculation_profiles WHERE id = NEW.profile_id) != 'draft' THEN
            RAISE EXCEPTION 'published profile factors are immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_published_profile_factor_no_update", "BEFORE UPDATE ON profile_factors", """
        IF (SELECT status FROM calculation_profiles WHERE id = OLD.profile_id) != 'draft'
           OR (SELECT status FROM calculation_profiles WHERE id = NEW.profile_id) != 'draft' THEN
            RAISE EXCEPTION 'published profile factors are immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    """),
    ("trg_published_profile_factor_no_delete", "BEFORE DELETE ON profile_factors", """
        IF (SELECT status FROM calculation_profiles WHERE id = OLD.profile_id) != 'draft' THEN
            RAISE EXCEPTION 'published profile factors are immutable'
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN OLD;
    """),
)


def immutability_trigger_ddl() -> list[str]:
    """CREATE OR REPLACE statements for every immutability trigger (repeatable)."""
    statements = []
    for name, timing, body in IMMUTABILITY_TRIGGERS:
        statements.append(
            f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$\n"
            f"    BEGIN{body}END;\n$$"
        )
        statements.append(
            f"CREATE OR REPLACE TRIGGER {name} {timing} "
            f"FOR EACH ROW EXECUTE FUNCTION {name}()"
        )
    return statements
