import re
import httpx
from typing import List, Dict, Optional, Callable
from urllib.parse import unquote
import tempfile
import os
import aiofiles
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class M3UParser:
    def __init__(self):
        self.channels = []
        self.progress_callback: Optional[Callable] = None
        
    async def parse_from_url(self, url: str, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """Download and parse M3U file with progress tracking"""
        self.progress_callback = progress_callback
        
        # Download to temporary file with progress
        temp_file = await self._download_with_progress(url)
        
        try:
            # Parse the downloaded file
            channels = self.parse_from_file(str(temp_file))
            return channels
        finally:
            # Clean up temp file
            if temp_file.exists():
                os.unlink(temp_file)
    
    async def _download_with_progress(self, url: str) -> Path:
        """Download file with progress tracking, handling dynamic URLs"""
        temp_file = Path(tempfile.mktemp(suffix='.m3u'))
        
        try:
            # Configure client with longer timeout for dynamic URLs
            timeout = httpx.Timeout(
                connect=30.0,
                read=300.0,
                write=30.0,
                pool=30.0
            )
            
            # Custom headers to appear as a legitimate client
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                # First, try a HEAD request to check if server supports it
                try:
                    head_response = await client.head(url, follow_redirects=True)
                    total_size = int(head_response.headers.get('content-length', 0))
                except:
                    total_size = 0
                
                if self.progress_callback:
                    await self.progress_callback(
                        status="connecting",
                        progress=0,
                        message="Connecting to server...",
                        details={"url": url}
                    )
                
                # For dynamic URLs that generate content, we might need to wait
                if self.progress_callback:
                    await self.progress_callback(
                        status="downloading",
                        progress=5,
                        message="Requesting playlist from server...",
                        details={"step": "request"}
                    )
                
                # Try direct download first (for dynamic generation URLs)
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code != 200:
                    raise Exception(f"Server returned status {response.status_code}")
                
                content_type = response.headers.get('content-type', '')
                logger.info(f"Content-Type: {content_type}")
                logger.info(f"Response size: {len(response.content)} bytes")
                
                # Write content to file
                async with aiofiles.open(temp_file, 'wb') as f:
                    await f.write(response.content)
                
                downloaded = len(response.content)
                
                if self.progress_callback:
                    await self.progress_callback(
                        status="downloading",
                        progress=50,
                        message=f"Downloaded playlist ({downloaded/1024/1024:.1f} MB)",
                        details={"downloaded": downloaded}
                    )
            
            # Verify the file is valid M3U
            if temp_file.stat().st_size == 0:
                raise Exception("Downloaded file is empty")
                
            # Check first line
            with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                if not first_line.startswith('#EXTM3U'):
                    logger.warning(f"File may not be M3U format. First line: {first_line[:100]}")
            
            return temp_file
            
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                os.unlink(temp_file)
            logger.error(f"Download failed: {str(e)}")
            raise Exception(f"Failed to download playlist: {str(e)}")
    
    def parse_from_file(self, file_path: str) -> List[Dict]:
        """Parse M3U file with progress tracking and category detection"""
        logger.info(f"Reading M3U file: {file_path}")
        file_size = Path(file_path).stat().st_size
        logger.info(f"File size: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        logger.info(f"Content length: {len(content)} characters")
        logger.info("Starting M3U content parsing")
        
        result = self.parse(content)
        
        logger.info(f"M3U parsing completed. Found {len(result)} channels")
        return result
    
    def parse(self, content: str) -> List[Dict]:
        """Parse M3U content with enhanced category detection"""
        logger.info("Starting M3U content parsing")
        self.channels = []
        lines = content.strip().split('\n')
        
        logger.info(f"Total lines to process: {len(lines)}")
        
        if not lines or not lines[0].startswith('#EXTM3U'):
            logger.error(f"Invalid M3U format. First line: {lines[0] if lines else 'EMPTY FILE'}")
            raise ValueError("Invalid M3U file format")
        
        logger.info("Valid M3U header found")
        current_category = None
        total_lines = len(lines)
        processed_channels = 0
        import time
        start_time = time.time()
        
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Log progress every 1000 lines
            if i % 1000 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                logger.info(f"Processing line {i}/{total_lines} ({rate:.0f} lines/sec, {processed_channels} channels found)")
            
            # Detect category markers
            if self._is_category_marker(line):
                current_category = self._extract_category(line)
                logger.info(f"Detected category: {current_category}")
            
            elif line.startswith('#EXTINF:'):
                channel_info = self._parse_extinf(line)
                
                # Use detected category if no group_title
                if current_category and not channel_info.get('group_title'):
                    channel_info['group_title'] = current_category
                
                # Get URL from next line
                i += 1
                if i < len(lines):
                    url = lines[i].strip()
                    if url and not url.startswith('#'):
                        channel_info['stream_url'] = url
                        self.channels.append(channel_info)
                        processed_channels += 1
                        
                        # Update progress during parsing
                        if self.progress_callback and processed_channels % 100 == 0:
                            progress = 50 + int((i / total_lines) * 50)  # 50-100% for parsing
                            import asyncio
                            asyncio.create_task(self.progress_callback(
                                status="parsing",
                                progress=progress,
                                message=f"Parsing channels ({processed_channels} found)",
                                details={"channels_found": processed_channels}
                            ))
            
            i += 1
        
        elapsed = time.time() - start_time
        logger.info(f"Line processing completed in {elapsed:.2f} seconds")
        logger.info(f"Found {processed_channels} channels before category enhancement")
        
        # Group channels by detected patterns
        logger.info("Starting category enhancement")
        self._enhance_categories()
        logger.info("Category enhancement completed")
        
        logger.info(f"Final result: {len(self.channels)} channels parsed")
        return self.channels
    
    def _is_category_marker(self, line: str) -> bool:
        """Detect if line is a category marker"""
        # Common category patterns
        patterns = [
            r'^#{3,}\s*(.+)\s*#{3,}',  # ### Category ###
            r'^#\s*[-=]{3,}\s*(.+)\s*[-=]{3,}',  # # --- Category ---
            r'^#\s*\*{3,}\s*(.+)\s*\*{3,}',  # # *** Category ***
            r'^#\s*GROUP:\s*(.+)',  # # GROUP: Category
            r'^#\s*CATEGORY:\s*(.+)',  # # CATEGORY: Category
            r'^####\s*(.+)',  # #### Category
            r'^#\s*\[(.+)\]',  # # [Category]
        ]
        
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return True
        return False
    
    def _extract_category(self, line: str) -> str:
        """Extract category name from marker line"""
        # Remove common decorators
        category = re.sub(r'[#\-=\*\[\]]+', '', line).strip()
        category = re.sub(r'^(GROUP|CATEGORY):\s*', '', category, flags=re.IGNORECASE).strip()
        return category
    
    def _enhance_categories(self):
        """Enhance category detection based on channel names"""
        logger.info("Starting category enhancement for channels without groups")
        enhanced_count = 0
        
        for channel in self.channels:
            if not channel.get('group_title'):
                # Try to detect category from channel name
                name = channel.get('name', '').upper()
                
                # Country detection
                countries = ['USA', 'UK', 'CANADA', 'AUSTRALIA', 'GERMANY', 'FRANCE', 'SPAIN', 'ITALY']
                for country in countries:
                    if country in name:
                        channel['group_title'] = country
                        break
                
                # Genre detection
                if not channel.get('group_title'):
                    genres = {
                        'SPORTS': ['SPORT', 'ESPN', 'NBA', 'NFL', 'NHL', 'MLB', 'UFC'],
                        'NEWS': ['NEWS', 'CNN', 'BBC', 'FOX NEWS', 'MSNBC'],
                        'MOVIES': ['MOVIE', 'CINEMA', 'HBO', 'SHOWTIME', 'CINEMAX'],
                        'KIDS': ['KIDS', 'CARTOON', 'DISNEY', 'NICKELODEON'],
                        'MUSIC': ['MUSIC', 'MTV', 'VH1', 'VEVO'],
                        'DOCUMENTARY': ['DISCOVERY', 'NATIONAL GEOGRAPHIC', 'HISTORY', 'ANIMAL PLANET']
                    }
                    
                    for genre, keywords in genres.items():
                        if any(keyword in name for keyword in keywords):
                            channel['group_title'] = genre
                            enhanced_count += 1
                            break
        
        logger.info(f"Category enhancement completed. Enhanced {enhanced_count} channels")
    
    def _parse_extinf(self, line: str) -> Dict:
        info = {
            'tvg_id': '',
            'tvg_name': '',
            'tvg_logo': '',
            'group_title': '',
            'name': '',
            'channel_number': '',
            'tvg_country': '',
            'tvg_language': ''
        }
        
        # Extract duration and attributes
        match = re.match(r'#EXTINF:(-?\d+)\s*(.*?),(.*)$', line)
        if not match:
            return info
        
        duration, attributes, name = match.groups()
        info['name'] = name.strip()
        info['duration'] = int(duration)
        
        # Parse attributes
        attr_pattern = r'(\w+[-\w]*)\s*=\s*"([^"]*)"'
        for match in re.finditer(attr_pattern, attributes):
            key, value = match.groups()
            key = key.lower().replace('-', '_')
            if key in info:
                info[key] = unquote(value)
        
        # Extract channel number from name if present
        number_match = re.match(r'^(\d+(?:\.\d+)?)\s*[-_\s]\s*(.+)$', info['name'])
        if number_match:
            info['channel_number'] = number_match.group(1)
            info['name'] = number_match.group(2)
        
        return info
    
    def filter_by_group(self, group: str) -> List[Dict]:
        return [ch for ch in self.channels if ch.get('group_title', '').lower() == group.lower()]
    
    def filter_by_name(self, pattern: str) -> List[Dict]:
        pattern_lower = pattern.lower()
        return [ch for ch in self.channels if pattern_lower in ch.get('name', '').lower()]
    
    def get_groups(self) -> List[str]:
        groups = set()
        for channel in self.channels:
            if channel.get('group_title'):
                groups.add(channel['group_title'])
        return sorted(list(groups))
    
    def export_channel_m3u(self, channel: Dict) -> str:
        extinf = f"#EXTINF:-1"
        
        # Add attributes
        if channel.get('tvg_id'):
            extinf += f' tvg-id="{channel["tvg_id"]}"'
        if channel.get('tvg_name'):
            extinf += f' tvg-name="{channel["tvg_name"]}"'
        if channel.get('tvg_logo'):
            extinf += f' tvg-logo="{channel["tvg_logo"]}"'
        if channel.get('group_title'):
            extinf += f' group-title="{channel["group_title"]}"'
        
        extinf += f',{channel["name"]}\n{channel["stream_url"]}'
        
        return f"#EXTM3U\n{extinf}"
    
    def export_filtered_m3u(self, channels: List[Dict]) -> str:
        output = "#EXTM3U\n"
        
        for channel in channels:
            extinf = f"#EXTINF:-1"
            
            if channel.get('tvg_id'):
                extinf += f' tvg-id="{channel["tvg_id"]}"'
            if channel.get('tvg_name'):
                extinf += f' tvg-name="{channel["tvg_name"]}"'
            if channel.get('tvg_logo'):
                extinf += f' tvg-logo="{channel["tvg_logo"]}"'
            if channel.get('group_title'):
                extinf += f' group-title="{channel["group_title"]}"'
            
            extinf += f',{channel["name"]}\n{channel["stream_url"]}\n'
            output += extinf
        
        return output