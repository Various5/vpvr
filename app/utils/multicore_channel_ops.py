"""
Multicore Channel Operations - Optimized bulk operations for channel management

This module provides multicore processing for channel operations like
bulk updates, EPG mapping, and channel analysis.
"""

import asyncio
import multiprocessing as mp
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
import re
from difflib import SequenceMatcher

from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from app.models import Channel, ChannelGroup
from app.utils.epg_auto_mapper import EPGChannel
from app.config import get_settings

logger = logging.getLogger(__name__)

# Get number of CPU cores
NUM_CORES = cpu_count()
logger.info(f"Multicore Channel Ops: Detected {NUM_CORES} CPU cores")

@dataclass
class BulkOperationResult:
    """Result from bulk channel operation"""
    success_count: int
    error_count: int
    errors: List[str]
    processing_time: float
    channels_per_second: float

class MultiCoreChannelOperations:
    """Handles bulk channel operations using multiple CPU cores"""
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or get_settings().DATABASE_URL
        self.num_workers = max(1, NUM_CORES - 1)
        self.batch_size = 100
        
        # Setup process pool
        self.executor = ProcessPoolExecutor(max_workers=self.num_workers)
        
        logger.info(f"MultiCore Channel Ops initialized with {self.num_workers} workers")
    
    async def bulk_update_channels(
        self,
        channel_ids: List[int],
        updates: Dict[str, Any],
        progress_callback: Optional[callable] = None
    ) -> BulkOperationResult:
        """Bulk update channels using multiple cores"""
        start_time = time.time()
        
        # Split channel IDs into batches
        batches = []
        for i in range(0, len(channel_ids), self.batch_size):
            batch = channel_ids[i:i + self.batch_size]
            batches.append(batch)
        
        logger.info(f"Updating {len(channel_ids)} channels in {len(batches)} batches")
        
        # Process batches in parallel
        loop = asyncio.get_event_loop()
        futures = []
        
        for batch in batches:
            future = loop.run_in_executor(
                self.executor,
                update_channels_batch,
                batch,
                updates,
                self.db_url
            )
            futures.append(future)
        
        # Collect results
        success_count = 0
        errors = []
        completed = 0
        
        for future in as_completed(futures):
            try:
                batch_success = await future
                success_count += batch_success
                completed += 1
                
                if progress_callback:
                    progress = (completed / len(batches)) * 100
                    await progress_callback(progress, f"Updated {success_count} channels")
                    
            except Exception as e:
                errors.append(str(e))
                logger.error(f"Batch update error: {e}")
        
        elapsed = time.time() - start_time
        
        return BulkOperationResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
            processing_time=elapsed,
            channels_per_second=success_count / elapsed if elapsed > 0 else 0
        )
    
    async def auto_map_epg_multicore(
        self,
        channel_ids: Optional[List[int]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Auto-map EPG channels using fuzzy matching across multiple cores"""
        start_time = time.time()
        
        # Get channels and EPG channels
        engine = create_engine(self.db_url, poolclass=NullPool)
        SessionLocal = sessionmaker(bind=engine)
        
        with SessionLocal() as session:
            # Get channels to map
            query = session.query(Channel).filter(Channel.epg_channel_id.is_(None))
            if channel_ids:
                query = query.filter(Channel.id.in_(channel_ids))
            channels = query.all()
            
            # Get all EPG channels
            epg_channels = session.query(EPGChannel).all()
            
            # Convert to dicts for multiprocessing
            channels_data = [
                {'id': c.id, 'name': c.name, 'tvg_id': c.tvg_id}
                for c in channels
            ]
            epg_data = [
                {'id': e.id, 'channel_id': e.channel_id, 'display_name': e.display_name}
                for e in epg_channels
            ]
        
        if not channels_data or not epg_data:
            return {
                'success': True,
                'mapped_count': 0,
                'message': 'No channels to map or no EPG channels available'
            }
        
        logger.info(f"Auto-mapping {len(channels_data)} channels against {len(epg_data)} EPG channels")
        
        # Split channels for parallel processing
        chunk_size = max(10, len(channels_data) // self.num_workers)
        chunks = []
        
        for i in range(0, len(channels_data), chunk_size):
            chunk = channels_data[i:i + chunk_size]
            chunks.append(chunk)
        
        # Process chunks in parallel
        loop = asyncio.get_event_loop()
        futures = []
        
        for chunk in chunks:
            future = loop.run_in_executor(
                self.executor,
                find_epg_matches_worker,
                chunk,
                epg_data
            )
            futures.append(future)
        
        # Collect mapping results
        all_mappings = []
        completed = 0
        
        for future in as_completed(futures):
            mappings = await future
            all_mappings.extend(mappings)
            completed += 1
            
            if progress_callback:
                progress = (completed / len(chunks)) * 80  # 0-80% for matching
                await progress_callback(progress, f"Matched {len(all_mappings)} channels")
        
        # Apply mappings in database
        if all_mappings:
            await self._apply_epg_mappings(all_mappings, progress_callback)
        
        elapsed = time.time() - start_time
        
        return {
            'success': True,
            'mapped_count': len(all_mappings),
            'total_channels': len(channels_data),
            'processing_time': elapsed,
            'channels_per_second': len(channels_data) / elapsed if elapsed > 0 else 0
        }
    
    async def _apply_epg_mappings(
        self,
        mappings: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None
    ):
        """Apply EPG mappings to database"""
        # Use thread pool for database operations
        with ThreadPoolExecutor(max_workers=4) as executor:
            loop = asyncio.get_event_loop()
            futures = []
            
            # Split mappings into batches
            batch_size = 50
            for i in range(0, len(mappings), batch_size):
                batch = mappings[i:i + batch_size]
                future = loop.run_in_executor(
                    executor,
                    apply_mappings_batch,
                    batch,
                    self.db_url
                )
                futures.append(future)
            
            # Wait for completion
            completed = 0
            for future in as_completed(futures):
                await future
                completed += 1
                
                if progress_callback:
                    progress = 80 + (completed / len(futures)) * 20  # 80-100%
                    await progress_callback(progress, f"Applied {completed} mapping batches")
    
    async def analyze_channel_quality_multicore(
        self,
        channel_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Analyze channel quality (names, logos, EPG mapping) using multiple cores"""
        start_time = time.time()
        
        # Get channels
        engine = create_engine(self.db_url, poolclass=NullPool)
        SessionLocal = sessionmaker(bind=engine)
        
        with SessionLocal() as session:
            query = session.query(Channel)
            if channel_ids:
                query = query.filter(Channel.id.in_(channel_ids))
            channels = query.all()
            
            channels_data = [
                {
                    'id': c.id,
                    'name': c.name,
                    'logo_url': c.logo_url,
                    'epg_channel_id': c.epg_channel_id,
                    'tvg_id': c.tvg_id,
                    'group_id': c.group_id
                }
                for c in channels
            ]
        
        # Analyze in parallel
        chunk_size = max(100, len(channels_data) // self.num_workers)
        chunks = []
        
        for i in range(0, len(channels_data), chunk_size):
            chunk = channels_data[i:i + chunk_size]
            chunks.append(chunk)
        
        loop = asyncio.get_event_loop()
        futures = []
        
        for chunk in chunks:
            future = loop.run_in_executor(
                self.executor,
                analyze_channels_worker,
                chunk
            )
            futures.append(future)
        
        # Aggregate results
        total_issues = []
        quality_scores = []
        
        for future in as_completed(futures):
            chunk_result = await future
            total_issues.extend(chunk_result['issues'])
            quality_scores.extend(chunk_result['scores'])
        
        avg_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        elapsed = time.time() - start_time
        
        # Group issues by type
        issues_by_type = {}
        for issue in total_issues:
            issue_type = issue['type']
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        return {
            'total_channels': len(channels_data),
            'average_quality_score': avg_score,
            'total_issues': len(total_issues),
            'issues_by_type': issues_by_type,
            'processing_time': elapsed,
            'channels_per_second': len(channels_data) / elapsed if elapsed > 0 else 0
        }
    
    async def _get_epg_channels_data(self, session: Session) -> List[Dict[str, Any]]:
        """Get EPG channel data from all active EPG sources"""
        epg_sources = session.query(EPGSource).filter(EPGSource.is_active == True).all()
        epg_channels_data = []
        
        xmltv_parser = XMLTVParser()
        
        for source in epg_sources:
            try:
                epg_data = await xmltv_parser.parse_from_url(source.url)
                for ch_id, ch_data in epg_data.get('channels', {}).items():
                    # Convert to dict format expected by workers
                    epg_channels_data.append({
                        'id': ch_id,
                        'channel_id': ch_id,
                        'display_name': ch_data.get('display_names', [''])[0] if ch_data.get('display_names') else ''
                    })
            except Exception as e:
                logger.error(f"Failed to parse EPG source {source.name}: {e}")
                continue
        
        return epg_channels_data
    
    def cleanup(self):
        """Cleanup resources"""
        self.executor.shutdown(wait=True)


# Worker functions for multiprocessing
def update_channels_batch(
    channel_ids: List[int],
    updates: Dict[str, Any],
    db_url: str
) -> int:
    """Worker function to update a batch of channels"""
    engine = create_engine(db_url, poolclass=NullPool)
    SessionLocal = sessionmaker(bind=engine)
    
    updated = 0
    
    with SessionLocal() as session:
        try:
            channels = session.query(Channel).filter(Channel.id.in_(channel_ids)).all()
            
            for channel in channels:
                for key, value in updates.items():
                    if hasattr(channel, key):
                        setattr(channel, key, value)
                updated += 1
            
            session.commit()
            return updated
            
        except Exception as e:
            session.rollback()
            logger.error(f"Batch update error: {str(e)}")
            raise


def find_epg_matches_worker(
    channels: List[Dict[str, Any]],
    epg_channels: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Worker function to find EPG matches for channels"""
    mappings = []
    
    for channel in channels:
        best_match = find_best_epg_match(channel, epg_channels)
        if best_match:
            mappings.append({
                'channel_id': channel['id'],
                'epg_channel_id': best_match['id'],
                'confidence': best_match['confidence']
            })
    
    return mappings


def find_best_epg_match(
    channel: Dict[str, Any],
    epg_channels: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Find best EPG match for a channel using fuzzy matching"""
    channel_name = normalize_channel_name(channel['name'])
    tvg_id = channel.get('tvg_id', '')
    
    best_match = None
    best_score = 0.0
    
    for epg in epg_channels:
        score = 0.0
        
        # Check TVG ID match first (highest priority)
        if tvg_id and tvg_id == epg.get('channel_id', ''):
            score = 1.0
        else:
            # Fuzzy match on names
            epg_name = normalize_channel_name(epg['display_name'])
            name_score = SequenceMatcher(None, channel_name, epg_name).ratio()
            
            # Boost score for exact matches after normalization
            if channel_name == epg_name:
                name_score = 0.95
            
            score = name_score
        
        if score > best_score and score >= 0.7:  # 70% threshold
            best_score = score
            best_match = {
                'id': epg['id'],
                'confidence': score
            }
    
    return best_match


def normalize_channel_name(name: str) -> str:
    """Normalize channel name for comparison"""
    # Convert to lowercase
    name = name.lower()
    
    # Remove common prefixes/suffixes
    patterns = [
        r'^(hd|sd|fhd|uhd|4k)\s+',
        r'\s+(hd|sd|fhd|uhd|4k)$',
        r'\s+\(.*\)$',
        r'\s+\[.*\]$',
        r'[^\w\s]',  # Remove special characters
    ]
    
    for pattern in patterns:
        name = re.sub(pattern, '', name)
    
    # Remove extra whitespace
    name = ' '.join(name.split())
    
    return name


def apply_mappings_batch(
    mappings: List[Dict[str, Any]],
    db_url: str
) -> int:
    """Apply EPG mappings to channels"""
    engine = create_engine(db_url, poolclass=NullPool)
    SessionLocal = sessionmaker(bind=engine)
    
    applied = 0
    
    with SessionLocal() as session:
        try:
            for mapping in mappings:
                channel = session.query(Channel).filter(
                    Channel.id == mapping['channel_id']
                ).first()
                
                if channel:
                    channel.epg_channel_id = mapping['epg_channel_id']
                    applied += 1
            
            session.commit()
            return applied
            
        except Exception as e:
            session.rollback()
            logger.error(f"Apply mappings error: {str(e)}")
            raise


def analyze_channels_worker(channels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze channel quality"""
    issues = []
    scores = []
    
    for channel in channels:
        channel_score = 100.0
        channel_issues = []
        
        # Check name quality
        name = channel.get('name', '')
        if not name:
            channel_issues.append({
                'type': 'missing_name',
                'channel_id': channel['id'],
                'severity': 'high'
            })
            channel_score -= 30
        elif len(name) < 3:
            channel_issues.append({
                'type': 'short_name',
                'channel_id': channel['id'],
                'name': name,
                'severity': 'medium'
            })
            channel_score -= 15
        
        # Check logo
        if not channel.get('logo_url'):
            channel_issues.append({
                'type': 'missing_logo',
                'channel_id': channel['id'],
                'severity': 'low'
            })
            channel_score -= 10
        
        # Check EPG mapping
        if not channel.get('epg_channel_id'):
            channel_issues.append({
                'type': 'no_epg_mapping',
                'channel_id': channel['id'],
                'severity': 'medium'
            })
            channel_score -= 20
        
        # Check group assignment
        if not channel.get('group_id'):
            channel_issues.append({
                'type': 'no_group',
                'channel_id': channel['id'],
                'severity': 'low'
            })
            channel_score -= 5
        
        issues.extend(channel_issues)
        scores.append(max(0, channel_score))
    
    return {
        'issues': issues,
        'scores': scores
    }