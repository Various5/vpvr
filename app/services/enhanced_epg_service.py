"""Enhanced EPG service with multiple source support and auto-mapping."""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import difflib
import re
from fuzzywuzzy import fuzz
import asyncio
import aiohttp
from app.models import (
    Channel, EPGSource, EPGProgram, EPGChannelMapping, 
    EPGImportLog
)
from app.utils.xmltv_parser import XMLTVParser
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EnhancedEPGService:
    def __init__(self, db: Session):
        self.db = db
        self.xmltv_parser = XMLTVParser()
        
    def get_epg_status(self) -> Dict:
        """Get comprehensive EPG status for all channels."""
        channels = self.db.query(Channel).filter(Channel.is_active == True).all()
        epg_sources = self.db.query(EPGSource).filter(EPGSource.is_active == True).all()
        
        channel_epg_status = []
        channels_with_epg = 0
        channels_without_epg = 0
        auto_mapped_count = 0
        manual_mapped_count = 0
        
        for channel in channels:
            # Check if channel has EPG data
            has_current_epg = self.db.query(EPGProgram).filter(
                and_(
                    EPGProgram.channel_id == channel.id,
                    EPGProgram.start_time <= datetime.utcnow(),
                    EPGProgram.end_time >= datetime.utcnow()
                )
            ).first() is not None
            
            # Get EPG mappings for this channel
            mappings = self.db.query(EPGChannelMapping).filter(
                EPGChannelMapping.channel_id == channel.id
            ).all()
            
            epg_sources_info = []
            for mapping in mappings:
                source = mapping.epg_source
                epg_sources_info.append({
                    'source_id': source.id,
                    'source_name': source.name,
                    'epg_channel_id': mapping.epg_channel_id,
                    'epg_channel_name': mapping.epg_channel_name,
                    'match_confidence': mapping.match_confidence,
                    'match_method': mapping.match_method,
                    'is_active': mapping.is_active
                })
            
            status = {
                'channel_id': channel.id,
                'channel_name': channel.name,
                'channel_number': channel.number,
                'has_epg': has_current_epg,
                'epg_auto_mapped': channel.epg_auto_mapped,
                'epg_mapping_locked': channel.epg_mapping_locked,
                'last_epg_update': channel.last_epg_update,
                'epg_sources': epg_sources_info,
                'mapping_count': len(mappings)
            }
            
            channel_epg_status.append(status)
            
            if has_current_epg:
                channels_with_epg += 1
            else:
                channels_without_epg += 1
                
            if channel.epg_auto_mapped:
                auto_mapped_count += 1
            elif len(mappings) > 0:
                manual_mapped_count += 1
        
        return {
            'summary': {
                'total_channels': len(channels),
                'channels_with_epg': channels_with_epg,
                'channels_without_epg': channels_without_epg,
                'auto_mapped_channels': auto_mapped_count,
                'manual_mapped_channels': manual_mapped_count,
                'total_epg_sources': len(epg_sources)
            },
            'channels': channel_epg_status,
            'epg_sources': [
                {
                    'id': source.id,
                    'name': source.name,
                    'type': source.type,
                    'priority': source.priority,
                    'channel_count': source.channel_count,
                    'program_count': source.program_count,
                    'last_updated': source.last_updated,
                    'import_status': source.import_status
                }
                for source in epg_sources
            ]
        }
    
    def auto_map_channels(self, epg_source_id: int, force: bool = False) -> Dict:
        """Automatically map channels to EPG data based on various matching algorithms."""
        epg_source = self.db.query(EPGSource).filter(EPGSource.id == epg_source_id).first()
        if not epg_source:
            raise ValueError(f"EPG source {epg_source_id} not found")
        
        if not epg_source.auto_map:
            return {'status': 'skipped', 'reason': 'Auto-mapping disabled for this source'}
        
        # Get channels that need mapping
        if force:
            channels = self.db.query(Channel).filter(
                Channel.is_active == True
            ).all()
        else:
            # Only map channels that aren't locked and don't have mappings
            channels = self.db.query(Channel).filter(
                and_(
                    Channel.is_active == True,
                    Channel.epg_mapping_locked == False
                )
            ).all()
        
        # Get EPG channels from the parsed data
        epg_channels = self._get_epg_channels_from_source(epg_source)
        
        results = {
            'total_channels': len(channels),
            'mapped': 0,
            'updated': 0,
            'failed': 0,
            'mappings': []
        }
        
        for channel in channels:
            # Skip if channel has a mapping and we're not forcing
            existing_mapping = self.db.query(EPGChannelMapping).filter(
                and_(
                    EPGChannelMapping.channel_id == channel.id,
                    EPGChannelMapping.epg_source_id == epg_source_id
                )
            ).first()
            
            if existing_mapping and not force:
                continue
            
            # Find best match
            best_match = self._find_best_epg_match(channel, epg_channels)
            
            if best_match and best_match['confidence'] >= 0.7:  # 70% confidence threshold
                if existing_mapping:
                    # Update existing mapping
                    existing_mapping.epg_channel_id = best_match['epg_channel_id']
                    existing_mapping.epg_channel_name = best_match['epg_channel_name']
                    existing_mapping.match_confidence = best_match['confidence']
                    existing_mapping.match_method = best_match['method']
                    existing_mapping.updated_at = datetime.utcnow()
                    results['updated'] += 1
                else:
                    # Create new mapping
                    mapping = EPGChannelMapping(
                        channel_id=channel.id,
                        epg_source_id=epg_source_id,
                        epg_channel_id=best_match['epg_channel_id'],
                        epg_channel_name=best_match['epg_channel_name'],
                        match_confidence=best_match['confidence'],
                        match_method=best_match['method'],
                        priority=epg_source.priority
                    )
                    self.db.add(mapping)
                    results['mapped'] += 1
                
                # Mark channel as auto-mapped
                channel.epg_auto_mapped = True
                
                results['mappings'].append({
                    'channel_name': channel.name,
                    'epg_channel_name': best_match['epg_channel_name'],
                    'confidence': best_match['confidence'],
                    'method': best_match['method']
                })
            else:
                results['failed'] += 1
        
        self.db.commit()
        return results
    
    def _find_best_epg_match(self, channel: Channel, epg_channels: List[Dict]) -> Optional[Dict]:
        """Find the best EPG channel match using multiple algorithms."""
        candidates = []
        
        channel_name = self._normalize_channel_name(channel.name)
        
        for epg_channel in epg_channels:
            epg_name = self._normalize_channel_name(epg_channel['name'])
            
            # Method 1: Exact match
            if channel_name == epg_name:
                return {
                    'epg_channel_id': epg_channel['id'],
                    'epg_channel_name': epg_channel['name'],
                    'confidence': 1.0,
                    'method': 'exact'
                }
            
            # Method 2: Fuzzy string matching
            ratio = fuzz.ratio(channel_name, epg_name)
            partial_ratio = fuzz.partial_ratio(channel_name, epg_name)
            token_sort_ratio = fuzz.token_sort_ratio(channel_name, epg_name)
            
            # Calculate weighted score
            score = (ratio * 0.4 + partial_ratio * 0.3 + token_sort_ratio * 0.3) / 100
            
            candidates.append({
                'epg_channel_id': epg_channel['id'],
                'epg_channel_name': epg_channel['name'],
                'confidence': score,
                'method': 'fuzzy'
            })
            
            # Method 3: Check if one name contains the other
            if channel_name in epg_name or epg_name in channel_name:
                candidates.append({
                    'epg_channel_id': epg_channel['id'],
                    'epg_channel_name': epg_channel['name'],
                    'confidence': 0.85,
                    'method': 'contains'
                })
            
            # Method 4: Check common patterns (HD, SD, etc.)
            if self._match_channel_variants(channel_name, epg_name):
                candidates.append({
                    'epg_channel_id': epg_channel['id'],
                    'epg_channel_name': epg_channel['name'],
                    'confidence': 0.9,
                    'method': 'variant'
                })
        
        # Return best candidate
        if candidates:
            return max(candidates, key=lambda x: x['confidence'])
        
        return None
    
    def _normalize_channel_name(self, name: str) -> str:
        """Normalize channel name for comparison."""
        # Convert to lowercase
        name = name.lower()
        
        # Remove common prefixes/suffixes
        patterns_to_remove = [
            r'^##\s*', r'\s*##$',  # Remove ## markers
            r'^\d+\s*[-\.]\s*',    # Remove channel numbers
            r'\s*\(\d+\)$',         # Remove numbers in parentheses
            r'\s*\[.*?\]',          # Remove content in brackets
            r'\s*\{.*?\}',          # Remove content in braces
            r'\s+hd$', r'\s+sd$',   # Remove HD/SD suffixes
            r'\s+4k$', r'\s+uhd$',  # Remove 4K/UHD suffixes
            r'\s+fhd$',             # Remove FHD suffix
            r'\s*\+$',              # Remove plus sign
            r'[^\w\s]',             # Remove special characters
        ]
        
        for pattern in patterns_to_remove:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        return name
    
    def _match_channel_variants(self, name1: str, name2: str) -> bool:
        """Check if two channel names are variants of each other."""
        # Common variant patterns
        variants = [
            (r'(\w+)\s*hd', r'\1'),          # HD variant
            (r'(\w+)\s*sd', r'\1'),          # SD variant
            (r'(\w+)\s*\+', r'\1 plus'),     # Plus variant
            (r'(\w+)\s*1', r'\1 one'),       # Number variants
            (r'(\w+)\s*2', r'\1 two'),
            (r'(\w+)\s*ii', r'\1 2'),        # Roman numeral variants
            (r'(\w+)\s*iii', r'\1 3'),
            (r'&', 'and'),                   # Ampersand variant
        ]
        
        for pattern, replacement in variants:
            # Check both directions
            if re.sub(pattern, replacement, name1, flags=re.IGNORECASE) == name2:
                return True
            if re.sub(pattern, replacement, name2, flags=re.IGNORECASE) == name1:
                return True
        
        return False
    
    def _get_epg_channels_from_source(self, epg_source: EPGSource) -> List[Dict]:
        """Get channel list from EPG source."""
        # This would be implemented based on the source type
        # For now, return empty list - would parse XMLTV or call API
        return []
    
    async def import_epg_data(self, epg_source_id: int) -> Dict:
        """Import EPG data from a source."""
        epg_source = self.db.query(EPGSource).filter(EPGSource.id == epg_source_id).first()
        if not epg_source:
            raise ValueError(f"EPG source {epg_source_id} not found")
        
        # Create import log
        import_log = EPGImportLog(
            epg_source_id=epg_source_id,
            started_at=datetime.utcnow(),
            status='in_progress'
        )
        self.db.add(import_log)
        self.db.commit()
        
        # Update source status
        epg_source.import_status = 'importing'
        self.db.commit()
        
        try:
            # Import based on source type
            if epg_source.type == 'xmltv':
                result = await self._import_xmltv_data(epg_source)
            else:
                raise ValueError(f"Unsupported EPG source type: {epg_source.type}")
            
            # Update import log
            import_log.completed_at = datetime.utcnow()
            import_log.status = 'success'
            import_log.channels_found = result.get('channels_found', 0)
            import_log.channels_mapped = result.get('channels_mapped', 0)
            import_log.programs_imported = result.get('programs_imported', 0)
            import_log.duration_seconds = int(
                (import_log.completed_at - import_log.started_at).total_seconds()
            )
            
            # Update source
            epg_source.import_status = 'completed'
            epg_source.last_updated = datetime.utcnow()
            epg_source.channel_count = result.get('channels_found', 0)
            epg_source.program_count = result.get('programs_imported', 0)
            epg_source.last_error = None
            
            self.db.commit()
            return result
            
        except Exception as e:
            logger.error(f"Error importing EPG data: {e}")
            
            # Update import log
            import_log.completed_at = datetime.utcnow()
            import_log.status = 'failed'
            import_log.errors = str(e)
            import_log.duration_seconds = int(
                (import_log.completed_at - import_log.started_at).total_seconds()
            )
            
            # Update source
            epg_source.import_status = 'failed'
            epg_source.last_error = str(e)
            
            self.db.commit()
            raise
    
    async def _import_xmltv_data(self, epg_source: EPGSource) -> Dict:
        """Import XMLTV EPG data."""
        # This would use the XMLTVParser to import data
        # For now, return a mock result
        return {
            'channels_found': 0,
            'channels_mapped': 0,
            'programs_imported': 0
        }
    
    def manual_map_channel(
        self, 
        channel_id: int, 
        epg_source_id: int, 
        epg_channel_id: str
    ) -> EPGChannelMapping:
        """Manually map a channel to an EPG source."""
        # Remove existing mapping if any
        existing = self.db.query(EPGChannelMapping).filter(
            and_(
                EPGChannelMapping.channel_id == channel_id,
                EPGChannelMapping.epg_source_id == epg_source_id
            )
        ).first()
        
        if existing:
            existing.epg_channel_id = epg_channel_id
            existing.match_method = 'manual'
            existing.match_confidence = 1.0
            existing.updated_at = datetime.utcnow()
            mapping = existing
        else:
            mapping = EPGChannelMapping(
                channel_id=channel_id,
                epg_source_id=epg_source_id,
                epg_channel_id=epg_channel_id,
                match_method='manual',
                match_confidence=1.0
            )
            self.db.add(mapping)
        
        # Update channel
        channel = self.db.query(Channel).filter(Channel.id == channel_id).first()
        if channel:
            channel.epg_auto_mapped = False
            channel.epg_mapping_locked = True
        
        self.db.commit()
        return mapping
    
    def remove_channel_mapping(self, channel_id: int, epg_source_id: int) -> bool:
        """Remove a channel's EPG mapping."""
        mapping = self.db.query(EPGChannelMapping).filter(
            and_(
                EPGChannelMapping.channel_id == channel_id,
                EPGChannelMapping.epg_source_id == epg_source_id
            )
        ).first()
        
        if mapping:
            self.db.delete(mapping)
            
            # Check if channel has any other mappings
            other_mappings = self.db.query(EPGChannelMapping).filter(
                EPGChannelMapping.channel_id == channel_id
            ).count()
            
            if other_mappings == 0:
                # Update channel if no other mappings exist
                channel = self.db.query(Channel).filter(Channel.id == channel_id).first()
                if channel:
                    channel.epg_auto_mapped = False
                    channel.epg_mapping_locked = False
            
            self.db.commit()
            return True
        
        return False