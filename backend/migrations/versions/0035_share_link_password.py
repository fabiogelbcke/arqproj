"""A share link's optional password, and its token kept encrypted (A37, 25 Oct 2026).

`password_hash`: the sender may protect a link with a password, which the supplier
types once per device. `token_encrypted`: staff copy any link from the project's
list (Fabio: only the device that made a link could). The app inserts both with
the link and never changes them, so its grants stay as 0034 left them. Links made
before have neither: no password, and only their device can copy them.

Revision: 0035
Previous: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("share_links", sa.Column("token_encrypted", sa.Text(), nullable=True))
    op.add_column("share_links", sa.Column("password_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("share_links", "password_hash")
    op.drop_column("share_links", "token_encrypted")
