"""per-client statistical model settings (sigma 1-5 visibility/info-only)

Revision ID: 4e5f6071a2b3
Revises: 3d4e5f6071a2
Create Date: 2026-08-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.core.statistical_model_defaults import default_statistical_model_rows


# revision identifiers, used by Alembic.
revision = '4e5f6071a2b3'
down_revision = '3d4e5f6071a2'
branch_labels = None
depends_on = None

# New table, plus a data backfill -- every client that existed before
# this table did gets the same 5 default rows a brand-new client gets
# from api/admin_clients.py's create_client (see
# core/statistical_model_defaults.py), so the app's behaviour for
# existing clients doesn't silently change the moment this deploys.


def upgrade():
    op.create_table(
        'statistical_model_settings',
        sa.Column('statistical_model_setting_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('sigma_level', sa.Integer(), nullable=False),
        sa.Column('visible', sa.Boolean(), nullable=False),
        sa.Column('info_only', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('statistical_model_setting_id'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.client_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('client_id', 'sigma_level', name='uq_stat_model_setting_client_sigma'),
    )

    conn = op.get_bind()
    client_ids = [row[0] for row in conn.execute(sa.text('SELECT client_id FROM clients'))]
    if not client_ids:
        return

    settings_table = sa.table(
        'statistical_model_settings',
        sa.column('client_id', sa.Integer),
        sa.column('sigma_level', sa.Integer),
        sa.column('visible', sa.Boolean),
        sa.column('info_only', sa.Boolean),
    )
    rows = [row for client_id in client_ids for row in default_statistical_model_rows(client_id)]
    op.bulk_insert(settings_table, rows)


def downgrade():
    op.drop_table('statistical_model_settings')
