"""Drive connection state on storage connections; the app may now change them.

Revision: 0009
Previous: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("storage_connections", sa.Column("account_email", sa.Text(), nullable=True))
    op.add_column("storage_connections", sa.Column("writer_token", sa.Text(), nullable=True))
    op.add_column(
        "storage_connections",
        sa.Column("writer_status", sa.Text(), server_default=sa.text("'none'"), nullable=False),
    )
    op.add_column(
        "storage_connections",
        sa.Column("reader_status", sa.Text(), server_default=sa.text("'unknown'"), nullable=False),
    )
    op.add_column("storage_connections", sa.Column("connected_by", sa.Uuid(), nullable=True))
    op.add_column(
        "storage_connections", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_check_constraint(
        op.f("ck_storage_connections_writer_status_known"),
        "storage_connections",
        "writer_status IN ('none', 'connected', 'expired')",
    )
    op.create_check_constraint(
        op.f("ck_storage_connections_reader_status_known"),
        "storage_connections",
        "reader_status IN ('unknown', 'ok', 'no_access')",
    )
    op.create_check_constraint(
        op.f("ck_storage_connections_connected_has_token"),
        "storage_connections",
        "writer_status <> 'connected' OR writer_token IS NOT NULL",
    )

    # Offices connect and disconnect Drive from the painel (owners only, checked
    # by the app); tenant isolation keeps each office to its own row.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'GRANT INSERT, UPDATE, DELETE ON storage_connections TO %I',
                current_database() || '_app'
            );
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'REVOKE INSERT, UPDATE, DELETE ON storage_connections FROM %I',
                current_database() || '_app'
            );
        END $$
        """
    )
    for name in ("connected_has_token", "reader_status_known", "writer_status_known"):
        op.drop_constraint(
            op.f(f"ck_storage_connections_{name}"), "storage_connections", type_="check"
        )
    op.drop_column("storage_connections", "checked_at")
    op.drop_column("storage_connections", "connected_by")
    op.drop_column("storage_connections", "reader_status")
    op.drop_column("storage_connections", "writer_status")
    op.drop_column("storage_connections", "writer_token")
    op.drop_column("storage_connections", "account_email")
