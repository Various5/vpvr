"""Add import_sources table

Revision ID: add_import_sources
Revises: 
Create Date: 2025-07-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_import_sources'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create import_sources table
    op.create_table('import_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('m3u_url', sa.Text(), nullable=True),
        sa.Column('m3u_file_path', sa.Text(), nullable=True),
        sa.Column('m3u_headers', sa.JSON(), nullable=True),
        sa.Column('epg_url', sa.Text(), nullable=True),
        sa.Column('epg_file_path', sa.Text(), nullable=True),
        sa.Column('epg_headers', sa.JSON(), nullable=True),
        sa.Column('epg_timezone', sa.String(), nullable=True, server_default='UTC'),
        sa.Column('import_settings', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('last_import_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_import_status', sa.String(), nullable=True),
        sa.Column('last_import_details', sa.JSON(), nullable=True),
        sa.Column('next_refresh_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_channels', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('active_channels', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('failed_channels', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_import_duration', sa.Integer(), nullable=True),
        sa.Column('auto_refresh', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('refresh_interval', sa.Integer(), nullable=True, server_default='86400'),
        sa.Column('refresh_time', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_hash', sa.String(), nullable=True),
        sa.Column('auth_type', sa.String(), nullable=True),
        sa.Column('auth_credentials', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_import_sources_id'), 'import_sources', ['id'], unique=False)
    op.create_index('idx_source_active', 'import_sources', ['is_active'], unique=False)
    op.create_index('idx_next_refresh', 'import_sources', ['next_refresh_at', 'is_active'], unique=False)
    
    # Create unique constraints
    op.create_unique_constraint('_source_urls_uc', 'import_sources', ['m3u_url', 'epg_url'])
    op.create_unique_constraint('_file_hash_uc', 'import_sources', ['file_hash'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_next_refresh', table_name='import_sources')
    op.drop_index('idx_source_active', table_name='import_sources')
    op.drop_index(op.f('ix_import_sources_id'), table_name='import_sources')
    
    # Drop table
    op.drop_table('import_sources')