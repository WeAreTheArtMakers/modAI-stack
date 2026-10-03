"""Enforce organization-wide membership uniqueness without mutating data."""
from alembic import op
import sqlalchemy as sa


revision = "0004_membership_invariants"
down_revision = "0003_enterprise_invitations"
branch_labels = None
depends_on = None

ORG_LEVEL_UNIQUE_INDEX = "uq_memberships_user_org_orglevel"


def upgrade():
    # PostgreSQL treats NULL values as distinct in an ordinary unique
    # constraint.  Do not silently choose a record when legacy duplicate
    # organization memberships exist: make an operator merge/remove duplicates
    # before retrying this migration.
    duplicate = op.get_bind().execute(sa.text("""
        SELECT user_id, organization_id
        FROM memberships
        WHERE workspace_id IS NULL
        GROUP BY user_id, organization_id
        HAVING COUNT(*) > 1
        LIMIT 1
    """)).first()
    if duplicate:
        raise RuntimeError(
            "Cannot add organization membership invariant: duplicate "
            "organization-level memberships exist. Remediate duplicate "
            "(user_id, organization_id) rows before rerunning the migration."
        )
    predicate = sa.text("workspace_id IS NULL")
    op.create_index(
        ORG_LEVEL_UNIQUE_INDEX,
        "memberships",
        ["user_id", "organization_id"],
        unique=True,
        postgresql_where=predicate,
        sqlite_where=predicate,
    )


def downgrade():
    op.drop_index(ORG_LEVEL_UNIQUE_INDEX, table_name="memberships")
