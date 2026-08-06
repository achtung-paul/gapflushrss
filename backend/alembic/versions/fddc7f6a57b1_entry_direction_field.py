"""entry direction field

Revision ID: fddc7f6a57b1
Revises: f705abf9d277
Create Date: 2026-08-06 12:56:59.215365

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'fddc7f6a57b1'
down_revision = 'f705abf9d277'
branch_labels = None
depends_on = None

# Manual fix: unlike a brand-new table (where SQLAlchemy creates the enum
# type as part of CREATE TABLE), adding an enum column to an existing
# table via ALTER TABLE needs the Postgres type created explicitly first
# -- op.add_column alone doesn't emit a CREATE TYPE.
direction_enum = postgresql.ENUM("X", "Y", "Z", "OTHER", name="direction")


def upgrade():
    direction_enum.create(op.get_bind())
    op.add_column("analysis_entries", sa.Column("direction", direction_enum, nullable=True))


def downgrade():
    op.drop_column("analysis_entries", "direction")
    direction_enum.drop(op.get_bind())
