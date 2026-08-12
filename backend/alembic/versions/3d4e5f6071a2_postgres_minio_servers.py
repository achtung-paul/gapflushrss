"""postgres and minio servers for client auto-provisioning

Revision ID: 3d4e5f6071a2
Revises: 2c3d4e5f6071
Create Date: 2026-08-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3d4e5f6071a2'
down_revision = '2c3d4e5f6071'
branch_labels = None
depends_on = None

# New tables only, plus two nullable traceability columns -- a simple,
# reversible migration (no data backfill, nothing to guard against
# concurrent use), unlike the last two hand-written ones on this chain.
# See models/postgres_server.py and models/minio_server.py.


def upgrade():
    op.create_table(
        'postgres_servers',
        sa.Column('postgres_server_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('admin_username', sa.String(length=255), nullable=False),
        sa.Column('encrypted_admin_password', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('postgres_server_id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'minio_servers',
        sa.Column('minio_server_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('secure', sa.Boolean(), nullable=False),
        sa.Column('root_access_key', sa.String(length=255), nullable=False),
        sa.Column('encrypted_root_secret_key', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('minio_server_id'),
        sa.UniqueConstraint('name'),
    )

    op.add_column('postgres_services', sa.Column('provisioned_from_server_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_postgres_services_provisioned_from_server_id', 'postgres_services',
        'postgres_servers', ['provisioned_from_server_id'], ['postgres_server_id'],
    )
    op.add_column('minio_services', sa.Column('provisioned_from_server_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_minio_services_provisioned_from_server_id', 'minio_services',
        'minio_servers', ['provisioned_from_server_id'], ['minio_server_id'],
    )


def downgrade():
    op.drop_constraint('fk_minio_services_provisioned_from_server_id', 'minio_services', type_='foreignkey')
    op.drop_column('minio_services', 'provisioned_from_server_id')
    op.drop_constraint('fk_postgres_services_provisioned_from_server_id', 'postgres_services', type_='foreignkey')
    op.drop_column('postgres_services', 'provisioned_from_server_id')
    op.drop_table('minio_servers')
    op.drop_table('postgres_servers')
