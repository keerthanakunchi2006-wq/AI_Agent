"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01

Creates all tables from the SQLAlchemy models. The authoritative schema lives in
``app.models``; this migration materialises it for production databases. For
SQLite local dev, ``app.database.init_db`` is used instead.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Import after alembic context is ready so the bind is available.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from app.database import Base
    from app import models  # noqa: F401  register tables

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from app.database import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
