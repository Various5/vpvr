"""Add EPG columns to channels table

Revision ID: 95be4b375e68
Revises: enhanced_epg_system
Create Date: 2025-07-25 09:02:15.536930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95be4b375e68'
down_revision: Union[str, None] = 'enhanced_epg_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    # Add new columns only - SQLite doesn't support ALTER COLUMN TYPE
    with op.batch_alter_table('channels') as batch_op:
        batch_op.add_column(sa.Column('epg_auto_mapped', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('epg_mapping_locked', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('last_epg_update', sa.DateTime(timezone=True), nullable=True))
    
    # Create new indexes
    try:
        op.create_index(op.f('ix_custom_playlists_id'), 'custom_playlists', ['id'], unique=False)
    except:
        pass  # Index might already exist
    
    try:
        op.drop_index('idx_channel_epg_mapping', table_name='epg_channel_mappings')
    except:
        pass  # Index might not exist
    
    try:
        op.create_index(op.f('ix_epg_channel_mappings_id'), 'epg_channel_mappings', ['id'], unique=False)
    except:
        pass  # Index might already exist
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'epg_programs', type_='foreignkey')
    op.drop_index(op.f('ix_epg_channel_mappings_id'), table_name='epg_channel_mappings')
    op.create_index('idx_channel_epg_mapping', 'epg_channel_mappings', ['channel_id', 'epg_source_id'], unique=False)
    op.drop_index(op.f('ix_custom_playlists_id'), table_name='custom_playlists')
    op.alter_column('custom_playlists', 'updated_at',
               existing_type=sa.DateTime(timezone=True),
               type_=sa.TIMESTAMP(),
               existing_nullable=True)
    op.alter_column('custom_playlists', 'created_at',
               existing_type=sa.DateTime(timezone=True),
               type_=sa.TIMESTAMP(),
               existing_nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
    op.alter_column('custom_playlists', 'name',
               existing_type=sa.String(),
               type_=sa.TEXT(),
               existing_nullable=False)
    op.alter_column('custom_playlists', 'id',
               existing_type=sa.INTEGER(),
               nullable=True,
               autoincrement=True)
    op.alter_column('channels', 'language',
               existing_type=sa.String(),
               type_=sa.TEXT(),
               existing_nullable=True)
    op.alter_column('channels', 'country',
               existing_type=sa.String(),
               type_=sa.TEXT(),
               existing_nullable=True)
    op.drop_column('channels', 'last_epg_update')
    op.drop_column('channels', 'epg_mapping_locked')
    op.drop_column('channels', 'epg_auto_mapped')
    # ### end Alembic commands ###
