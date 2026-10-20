"""Add versioned carbon policies and nullable provenance to existing results."""
from alembic import op
import sqlalchemy as sa
from migrations.carbon_v2_guards import IMMUTABILITY_TRIGGERS, immutability_trigger_ddl

revision = "c7d2e0180001"
down_revision = "a28c2a50b363"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("material_factors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factor_key", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("value_decimal", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("product_form", sa.String(), nullable=False),
        sa.Column("production_system", sa.String(), nullable=False),
        sa.Column("geography", sa.String(), nullable=False),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("data_years_json", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("source_locator", sa.String(), nullable=False),
        sa.Column("evidence_type", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("usage_scope", sa.String(), nullable=False),
        sa.Column("limitations_json", sa.Text(), nullable=False),
        sa.Column("carbon_accounting_json", sa.Text(), nullable=False),
        sa.Column("components_json", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("review_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("factor_key", "version"),
        sa.CheckConstraint("review_status IN ('candidate', 'selected', 'rejected')", name="factor_review_status"),
        sa.CheckConstraint("evidence_type IN ('literature', 'derived', 'placeholder')", name="factor_evidence_type"))
    op.create_table("calculation_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("formula_version", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("usage_scope", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", "version"),
        sa.CheckConstraint("status IN ('draft', 'active', 'retired')", name="profile_status"))
    op.create_index("uq_active_carbon_profile", "calculation_profiles", ["usage_scope"],
                    unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table("profile_factors",
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("calculation_profiles.id"), primary_key=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("materials.id"), primary_key=True),
        sa.Column("factor_id", sa.Integer(), sa.ForeignKey("material_factors.id"), nullable=False),
        sa.Column("selection_assumption", sa.Text(), nullable=False))
    for name, column_type in (
        ("result_kind", sa.String()), ("formula_version", sa.String()),
        ("profile_id", sa.Integer()), ("snapshot_schema_version", sa.Integer()),
        ("calculation_snapshot_json", sa.Text()), ("client_request_id", sa.String()),
        ("request_hash", sa.String())):
        op.add_column("analysis_results", sa.Column(name, column_type, nullable=True))
    op.create_foreign_key("fk_analysis_results_profile_id_calculation_profiles",
                          "analysis_results", "calculation_profiles", ["profile_id"], ["id"])
    op.create_index("uq_analysis_request", "analysis_results",
                    ["user_id", "client_request_id"], unique=True)
    for statement in immutability_trigger_ddl():
        op.execute(sa.text(statement))


def downgrade():
    # Provenance and selected policy evidence must never be silently erased.
    if op.get_context().as_sql:
        raise RuntimeError("Carbon V2 downgrade requires an online data-preservation check.")
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM material_factors) "
        "OR EXISTS(SELECT 1 FROM calculation_profiles) "
        "OR EXISTS(SELECT 1 FROM analysis_results WHERE calculation_snapshot_json IS NOT NULL "
        "OR result_kind IS NOT NULL OR formula_version IS NOT NULL OR profile_id IS NOT NULL "
        "OR snapshot_schema_version IS NOT NULL OR client_request_id IS NOT NULL OR request_hash IS NOT NULL)"
    )).scalar_one():
        raise RuntimeError("Carbon V2 data exists; preserve it before downgrading.")
    for name, timing, _ in reversed(IMMUTABILITY_TRIGGERS):
        table = timing.split(" ON ")[1]
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {name} ON {table}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {name}()"))
    op.drop_index("uq_analysis_request", table_name="analysis_results")
    op.drop_constraint("fk_analysis_results_profile_id_calculation_profiles",
                        "analysis_results", type_="foreignkey")
    for name in ("request_hash", "client_request_id", "calculation_snapshot_json",
                 "snapshot_schema_version", "profile_id", "formula_version", "result_kind"):
        op.drop_column("analysis_results", name)
    op.drop_table("profile_factors")
    op.drop_index("uq_active_carbon_profile", table_name="calculation_profiles")
    op.drop_table("calculation_profiles")
    op.drop_table("material_factors")
