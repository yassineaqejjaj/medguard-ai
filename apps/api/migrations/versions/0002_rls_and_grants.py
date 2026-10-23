"""row level security, grants, append-only tables

Revision ID: 0002
Revises: 0001
"""
import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "users", "ai_systems", "ai_system_versions", "test_suites", "test_cases", "evaluation_runs",
    "evidence_objects", "run_items", "criterion_results", "reviews", "review_resolutions",
    "gate_policies", "gate_evaluations", "release_decisions", "reports", "audit_log", "api_tokens",
]
APPEND_ONLY = {"audit_log", "reviews", "release_decisions", "gate_evaluations"}
APP_ROLE = "medguard_app"
# Dev default only; compose/production set MEDGUARD_APP_DB_PASSWORD.
APP_PASSWORD = os.environ.get("MEDGUARD_APP_DB_PASSWORD", "medguard_app").replace("'", "''")
SETTING = "NULLIF(current_setting('app.org_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{APP_PASSWORD}';
      END IF;
    END $$;""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} USING (org_id = {SETTING}) WITH CHECK (org_id = {SETTING})"
        )
        privs = "SELECT, INSERT" if t in APPEND_ONLY else "SELECT, INSERT, UPDATE, DELETE"
        op.execute(f"GRANT {privs} ON {t} TO {APP_ROLE}")

    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON organizations USING (id = {SETTING}) WITH CHECK (id = {SETTING})")
    op.execute(f"GRANT SELECT, UPDATE ON organizations TO {APP_ROLE}")

    # Resolve a tenant from the token's org slug before a tenant context exists.
    op.execute("""
    CREATE FUNCTION org_id_by_slug(p_slug text) RETURNS uuid
    LANGUAGE sql SECURITY DEFINER SET search_path = public AS
    $$ SELECT id FROM organizations WHERE slug = p_slug $$;""")
    op.execute(f"GRANT EXECUTE ON FUNCTION org_id_by_slug(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS org_id_by_slug(text)")
    for t in TENANT_TABLES + ["organizations"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
