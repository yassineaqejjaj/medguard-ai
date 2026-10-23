"""resolve a tenant from a CI token hash before a tenant context exists

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION org_id_by_token_hash(p_hash text) RETURNS uuid
    LANGUAGE sql SECURITY DEFINER SET search_path = public AS
    $$ SELECT org_id FROM api_tokens WHERE token_hash = p_hash $$;""")
    op.execute("GRANT EXECUTE ON FUNCTION org_id_by_token_hash(text) TO medguard_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS org_id_by_token_hash(text)")
