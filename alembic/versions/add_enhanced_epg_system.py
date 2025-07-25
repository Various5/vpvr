"""Add enhanced EPG system with multiple sources and auto-mapping

Revision ID: enhanced_epg_system
Revises: add_import_sources_table
Create Date: 2025-07-25 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'enhanced_epg_system'
down_revision = 'add_import_sources'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create EPG channel mapping table
    op.create_table('epg_channel_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('epg_source_id', sa.Integer(), nullable=False),
        sa.Column('epg_channel_id', sa.String(), nullable=False),
        sa.Column('epg_channel_name', sa.String(), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('match_method', sa.String(), nullable=True),  # 'exact', 'fuzzy', 'manual'
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['epg_source_id'], ['epg_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_channel_epg_mapping', 'epg_channel_mappings', ['channel_id', 'epg_source_id'])
    
    # Add new columns to epg_sources table
    op.add_column('epg_sources', sa.Column('priority', sa.Integer(), default=0))
    op.add_column('epg_sources', sa.Column('type', sa.String(), default='xmltv'))  # xmltv, json, api
    op.add_column('epg_sources', sa.Column('auto_map', sa.Boolean(), default=True))
    op.add_column('epg_sources', sa.Column('last_error', sa.Text(), nullable=True))
    op.add_column('epg_sources', sa.Column('channel_count', sa.Integer(), default=0))
    op.add_column('epg_sources', sa.Column('program_count', sa.Integer(), default=0))
    op.add_column('epg_sources', sa.Column('import_status', sa.String(), default='idle'))  # idle, importing, completed, failed
    
    # Add epg_source_id to epg_programs to track which source the program came from
    with op.batch_alter_table('epg_programs') as batch_op:
        batch_op.add_column(sa.Column('epg_source_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('original_channel_id', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_epg_programs_source', 'epg_sources', ['epg_source_id'], ['id'], ondelete='SET NULL')
    
    # Create EPG import logs table
    op.create_table('epg_import_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('epg_source_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False),  # 'success', 'failed', 'partial'
        sa.Column('channels_found', sa.Integer(), default=0),
        sa.Column('channels_mapped', sa.Integer(), default=0),
        sa.Column('programs_imported', sa.Integer(), default=0),
        sa.Column('errors', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['epg_source_id'], ['epg_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add EPG-related columns to channels table
    op.add_column('channels', sa.Column('epg_auto_mapped', sa.Boolean(), default=False))
    op.add_column('channels', sa.Column('epg_mapping_locked', sa.Boolean(), default=False))
    op.add_column('channels', sa.Column('last_epg_update', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove EPG-related columns from channels table
    op.drop_column('channels', 'last_epg_update')
    op.drop_column('channels', 'epg_mapping_locked')
    op.drop_column('channels', 'epg_auto_mapped')
    
    # Drop EPG import logs table
    op.drop_table('epg_import_logs')
    
    # Remove columns from epg_programs
    with op.batch_alter_table('epg_programs') as batch_op:
        batch_op.drop_constraint('fk_epg_programs_source', type_='foreignkey')
        batch_op.drop_column('original_channel_id')
        batch_op.drop_column('epg_source_id')
    
    # Remove columns from epg_sources
    op.drop_column('epg_sources', 'import_status')
    op.drop_column('epg_sources', 'program_count')
    op.drop_column('epg_sources', 'channel_count')
    op.drop_column('epg_sources', 'last_error')
    op.drop_column('epg_sources', 'auto_map')
    op.drop_column('epg_sources', 'type')
    op.drop_column('epg_sources', 'priority')
    
    # Drop EPG channel mapping table
    op.drop_index('idx_channel_epg_mapping', table_name='epg_channel_mappings')
    op.drop_table('epg_channel_mappings')