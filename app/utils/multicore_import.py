"""
Multicore Import Manager - Optimized for parallel processing

This module provides multicore processing capabilities for channel imports,
utilizing all available CPU cores for faster parsing and database operations.
"""

import asyncio
import multiprocessing as mp
from multiprocessing import Pool, Queue, Manager, cpu_count
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
import json
import os
from datetime import datetime
import threading
import queue

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Channel, Playlist
from app.config import get_settings

logger = logging.getLogger(__name__)

# Get number of CPU cores
NUM_CORES = cpu_count()
logger.info(f"Multicore Import: Detected {NUM_CORES} CPU cores")

@dataclass
class ParseResult:
    """Result from parsing a chunk of M3U data"""
    channels: List[Dict[str, Any]]
    errors: List[str]
    chunk_id: int
    processing_time: float

class MultiCoreImportManager:
    """Manages imports using multiple CPU cores for parallel processing"""
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or get_settings().DATABASE_URL
        self.num_workers = max(1, NUM_CORES - 1)  # Leave one core for main process
        self.chunk_size = 1000  # Number of channels per chunk
        
        # Setup process pool
        self.executor = ProcessPoolExecutor(max_workers=self.num_workers)
        
        # For progress tracking
        self.manager = Manager()
        self.progress_queue = self.manager.Queue()
        self.stats = self.manager.dict()
        
        logger.info(f"MultiCore Import initialized with {self.num_workers} workers")
    
    async def import_playlist_multicore(
        self, 
        playlist_id: int, 
        m3u_content: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Import playlist using multiple cores"""
        start_time = time.time()
        
        # Initialize stats
        self.stats['total_channels'] = 0
        self.stats['processed_channels'] = 0
        self.stats['errors'] = 0
        self.stats['chunks_completed'] = 0
        
        try:
            # Parse M3U content into chunks
            logger.info("Splitting M3U content into chunks...")
            chunks = self._split_m3u_content(m3u_content)
            total_chunks = len(chunks)
            
            logger.info(f"Created {total_chunks} chunks for parallel processing")
            
            if progress_callback:
                await progress_callback(10, f"Processing {total_chunks} chunks on {self.num_workers} cores...")
            
            # Process chunks in parallel
            results = await self._process_chunks_parallel(chunks, playlist_id, progress_callback)
            
            # Merge results
            all_channels = []
            total_errors = []
            
            for result in results:
                all_channels.extend(result.channels)
                total_errors.extend(result.errors)
            
            # Batch insert channels
            if all_channels:
                await self._batch_insert_channels(all_channels, playlist_id, progress_callback)
            
            elapsed_time = time.time() - start_time
            
            return {
                'success': True,
                'total_channels': len(all_channels),
                'errors': len(total_errors),
                'processing_time': elapsed_time,
                'channels_per_second': len(all_channels) / elapsed_time if elapsed_time > 0 else 0,
                'cores_used': self.num_workers
            }
            
        except Exception as e:
            logger.error(f"Multicore import failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def _split_m3u_content(self, content: str) -> List[List[str]]:
        """Split M3U content into chunks for parallel processing"""
        lines = content.strip().split('\n')
        
        # Skip header if present
        if lines and lines[0].startswith('#EXTM3U'):
            lines = lines[1:]
        
        # Group lines into channel entries
        channels = []
        current_channel_lines = []
        
        for line in lines:
            if line.startswith('#EXTINF:'):
                if current_channel_lines:
                    channels.append(current_channel_lines)
                current_channel_lines = [line]
            elif current_channel_lines:
                current_channel_lines.append(line)
                if not line.startswith('#'):  # URL line
                    channels.append(current_channel_lines)
                    current_channel_lines = []
        
        # Handle last channel if any
        if current_channel_lines:
            channels.append(current_channel_lines)
        
        # Split into chunks
        chunks = []
        for i in range(0, len(channels), self.chunk_size):
            chunk = channels[i:i + self.chunk_size]
            chunks.append(chunk)
        
        self.stats['total_channels'] = len(channels)
        
        return chunks
    
    async def _process_chunks_parallel(
        self, 
        chunks: List[List[List[str]]], 
        playlist_id: int,
        progress_callback: Optional[Callable]
    ) -> List[ParseResult]:
        """Process chunks in parallel using multiple cores"""
        loop = asyncio.get_event_loop()
        futures = []
        
        # Submit chunks to process pool
        for i, chunk in enumerate(chunks):
            future = loop.run_in_executor(
                self.executor,
                parse_chunk_worker,
                chunk,
                i,
                playlist_id,
                self.db_url
            )
            futures.append(future)
        
        # Monitor progress
        results = []
        completed = 0
        total = len(chunks)
        
        for future in asyncio.as_completed(futures):
            result = await future
            results.append(result)
            completed += 1
            
            # Update progress
            progress = 10 + (completed / total * 50)  # 10-60% for parsing
            if progress_callback:
                await progress_callback(
                    progress, 
                    f"Parsed {completed}/{total} chunks ({result.channels} channels)"
                )
            
            logger.info(f"Chunk {result.chunk_id} completed in {result.processing_time:.2f}s")
        
        return results
    
    async def _batch_insert_channels(
        self, 
        channels: List[Dict[str, Any]], 
        playlist_id: int,
        progress_callback: Optional[Callable]
    ):
        """Batch insert channels using multiple database connections"""
        # Split channels for parallel insertion
        batch_size = 500
        batches = []
        
        for i in range(0, len(channels), batch_size):
            batch = channels[i:i + batch_size]
            batches.append(batch)
        
        logger.info(f"Inserting {len(channels)} channels in {len(batches)} batches")
        
        # Use thread pool for database operations
        with ThreadPoolExecutor(max_workers=min(4, self.num_workers)) as executor:
            loop = asyncio.get_event_loop()
            futures = []
            
            for i, batch in enumerate(batches):
                future = loop.run_in_executor(
                    executor,
                    insert_channels_batch,
                    batch,
                    playlist_id,
                    self.db_url
                )
                futures.append(future)
            
            # Wait for all insertions
            completed = 0
            total = len(batches)
            
            for future in asyncio.as_completed(futures):
                await future
                completed += 1
                
                progress = 60 + (completed / total * 40)  # 60-100% for insertion
                if progress_callback:
                    await progress_callback(
                        progress,
                        f"Inserted {completed}/{total} batches"
                    )
    
    def cleanup(self):
        """Cleanup resources"""
        self.executor.shutdown(wait=True)


# Worker functions for multiprocessing
def parse_chunk_worker(
    chunk: List[List[str]], 
    chunk_id: int, 
    playlist_id: int,
    db_url: str
) -> ParseResult:
    """Worker function to parse a chunk of M3U data"""
    start_time = time.time()
    channels = []
    errors = []
    
    try:
        for channel_lines in chunk:
            try:
                channel_data = parse_channel_entry(channel_lines, playlist_id)
                if channel_data:
                    channels.append(channel_data)
            except Exception as e:
                errors.append(f"Error parsing channel: {str(e)}")
        
    except Exception as e:
        errors.append(f"Chunk {chunk_id} error: {str(e)}")
    
    return ParseResult(
        channels=channels,
        errors=errors,
        chunk_id=chunk_id,
        processing_time=time.time() - start_time
    )


def parse_channel_entry(lines: List[str], playlist_id: int) -> Optional[Dict[str, Any]]:
    """Parse a single channel entry from M3U lines"""
    if not lines:
        return None
    
    # Parse EXTINF line
    extinf_line = lines[0]
    if not extinf_line.startswith('#EXTINF:'):
        return None
    
    # Extract channel info
    channel_data = {
        'playlist_id': playlist_id,
        'is_active': True
    }
    
    # Parse EXTINF attributes
    extinf_parts = extinf_line.split(',', 1)
    if len(extinf_parts) > 1:
        channel_data['name'] = extinf_parts[1].strip()
    
    # Parse attributes
    attr_part = extinf_parts[0].replace('#EXTINF:', '').strip()
    
    # Extract tvg attributes
    import re
    
    # tvg-id
    tvg_id_match = re.search(r'tvg-id="([^"]*)"', attr_part)
    if tvg_id_match:
        channel_data['tvg_id'] = tvg_id_match.group(1)
    
    # tvg-name
    tvg_name_match = re.search(r'tvg-name="([^"]*)"', attr_part)
    if tvg_name_match:
        channel_data['tvg_name'] = tvg_name_match.group(1)
    
    # tvg-logo
    tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', attr_part)
    if tvg_logo_match:
        channel_data['logo_url'] = tvg_logo_match.group(1)
    
    # group-title
    group_match = re.search(r'group-title="([^"]*)"', attr_part)
    if group_match:
        channel_data['group_name'] = group_match.group(1)
    
    # Get URL (last non-comment line)
    for line in reversed(lines):
        if not line.startswith('#'):
            channel_data['stream_url'] = line.strip()
            break
    
    # Extract codec info if available
    for line in lines:
        if line.startswith('#EXTGRP:'):
            channel_data['group_name'] = line.replace('#EXTGRP:', '').strip()
        elif line.startswith('#EXTVLCOPT:'):
            # Parse VLC options if needed
            pass
    
    return channel_data


def insert_channels_batch(
    channels: List[Dict[str, Any]], 
    playlist_id: int,
    db_url: str
) -> int:
    """Insert a batch of channels into the database"""
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    
    inserted = 0
    
    with SessionLocal() as session:
        try:
            for channel_data in channels:
                # Check if channel already exists
                existing = session.query(Channel).filter_by(
                    playlist_id=playlist_id,
                    stream_url=channel_data.get('stream_url')
                ).first()
                
                if existing:
                    # Update existing channel
                    for key, value in channel_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                else:
                    # Create new channel
                    channel = Channel(**channel_data)
                    session.add(channel)
                    inserted += 1
            
            session.commit()
            return inserted
            
        except Exception as e:
            session.rollback()
            logger.error(f"Batch insert error: {str(e)}")
            raise
        finally:
            session.close()


# Utility function to integrate with existing import flow
async def optimize_import_with_multicore(
    playlist_id: int,
    m3u_content: str,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Helper function to use multicore import with existing import flow"""
    manager = MultiCoreImportManager()
    
    try:
        result = await manager.import_playlist_multicore(
            playlist_id,
            m3u_content,
            progress_callback
        )
        return result
    finally:
        manager.cleanup()