"""standard tolerances table

Revision ID: b913c459029f
Revises: 10f7a2bf68cd
Create Date: 2026-08-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b913c459029f'
down_revision = '10f7a2bf68cd'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'standard_tolerances',
        sa.Column('standard_tolerance_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('tolerance_value', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('updated_by_username', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('standard_tolerance_id'),
        sa.UniqueConstraint('project_id', 'name'),
    )
    op.create_index(
        op.f('ix_standard_tolerances_project_id'), 'standard_tolerances', ['project_id'], unique=False
    )


def downgrade():
    op.drop_index(op.f('ix_standard_tolerances_project_id'), table_name='standard_tolerances')
    op.drop_table('standard_tolerances')
