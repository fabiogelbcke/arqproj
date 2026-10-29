"""One-time links to create an office from Unio's address (A38, A36).

An operator makes a link; its holder names the office and its address, and the
app creates both through the operator role, as the dashboard does. Grants the
operator role only this table; the app role gets nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_signup_links",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_office_signup_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_office_signup_links_token_hash")),
    )
    op.execute("""
        DO $$
        DECLARE operator_role text := current_database() || '_operator';
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT ON office_signup_links TO %I', operator_role);
            EXECUTE format('GRANT UPDATE (used_at, created_tenant_id) ON office_signup_links TO %I',
                           operator_role);
        END $$
    """)


def downgrade() -> None:
    op.drop_table("office_signup_links")
