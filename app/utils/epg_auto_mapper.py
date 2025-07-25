import re
import difflib
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.models.channel import Channel
from app.models.epg import EPGProgram
import logging

logger = logging.getLogger(__name__)

@dataclass
class EPGChannel:
    id: str
    display_names: List[str]
    icon: Optional[str] = None

@dataclass
class ChannelMatch:
    channel_id: int
    epg_channel_id: str
    confidence: float
    match_type: str  # 'exact', 'fuzzy', 'partial', 'icon'
    matched_on: str  # what field was matched

class EPGAutoMapper:
    def __init__(self, db: Session):
        self.db = db
        
    def auto_map_channels(self, epg_channels: List[EPGChannel]) -> List[ChannelMatch]:
        """Auto-map channels to EPG data using multiple matching strategies"""
        channels = self.db.query(Channel).filter(Channel.is_active == True).all()
        matches = []
        
        for channel in channels:
            best_match = self._find_best_match(channel, epg_channels)
            if best_match and best_match.confidence >= 0.6:  # Minimum confidence threshold
                matches.append(best_match)
                logger.info(f"Mapped channel '{channel.name}' to EPG '{best_match.epg_channel_id}' "
                          f"(confidence: {best_match.confidence:.2f}, type: {best_match.match_type})")
        
        return matches
    
    def _find_best_match(self, channel: Channel, epg_channels: List[EPGChannel]) -> Optional[ChannelMatch]:
        """Find the best EPG match for a channel using multiple strategies"""
        candidates = []
        
        # Strategy 1: Exact ID match
        if channel.epg_channel_id:
            for epg_ch in epg_channels:
                if epg_ch.id == channel.epg_channel_id:
                    candidates.append(ChannelMatch(
                        channel_id=channel.id,
                        epg_channel_id=epg_ch.id,
                        confidence=1.0,
                        match_type='exact',
                        matched_on='epg_channel_id'
                    ))
        
        # Strategy 2: Exact name match
        channel_name_clean = self._clean_name(channel.name)
        for epg_ch in epg_channels:
            for display_name in epg_ch.display_names:
                epg_name_clean = self._clean_name(display_name)
                if channel_name_clean == epg_name_clean:
                    candidates.append(ChannelMatch(
                        channel_id=channel.id,
                        epg_channel_id=epg_ch.id,
                        confidence=0.95,
                        match_type='exact',
                        matched_on='name'
                    ))
        
        # Strategy 3: Fuzzy name matching
        for epg_ch in epg_channels:
            for display_name in epg_ch.display_names:
                similarity = self._calculate_similarity(channel.name, display_name)
                if similarity >= 0.8:
                    candidates.append(ChannelMatch(
                        channel_id=channel.id,
                        epg_channel_id=epg_ch.id,
                        confidence=similarity * 0.9,  # Slightly lower than exact
                        match_type='fuzzy',
                        matched_on='name'
                    ))
        
        # Strategy 4: Partial name matching (contains)
        for epg_ch in epg_channels:
            for display_name in epg_ch.display_names:
                if self._partial_match(channel.name, display_name):
                    similarity = self._calculate_similarity(channel.name, display_name)
                    candidates.append(ChannelMatch(
                        channel_id=channel.id,
                        epg_channel_id=epg_ch.id,
                        confidence=min(similarity * 0.8, 0.85),  # Lower confidence for partial
                        match_type='partial',
                        matched_on='name'
                    ))
        
        # Strategy 5: Channel number matching
        if channel.number:
            for epg_ch in epg_channels:
                for display_name in epg_ch.display_names:
                    if self._number_match(channel.number, display_name):
                        candidates.append(ChannelMatch(
                            channel_id=channel.id,
                            epg_channel_id=epg_ch.id,
                            confidence=0.75,
                            match_type='partial',
                            matched_on='number'
                        ))
        
        # Strategy 6: Icon URL matching
        if channel.logo_url:
            for epg_ch in epg_channels:
                if epg_ch.icon and self._icon_match(channel.logo_url, epg_ch.icon):
                    candidates.append(ChannelMatch(
                        channel_id=channel.id,
                        epg_channel_id=epg_ch.id,
                        confidence=0.7,
                        match_type='icon',
                        matched_on='icon'
                    ))
        
        # Return the best candidate
        if candidates:
            return max(candidates, key=lambda x: x.confidence)
        
        return None
    
    def _clean_name(self, name: str) -> str:
        """Clean channel name for better matching"""
        # Convert to lowercase
        name = name.lower().strip()
        
        # Remove common prefixes/suffixes
        patterns_to_remove = [
            r'^(the\s+)',
            r'\s+(hd|sd|4k|uhd)$',
            r'\s+(tv|channel|ch)$',
            r'\s+\d+$',  # Remove trailing numbers
            r'[^\w\s]',  # Remove special characters
        ]
        
        for pattern in patterns_to_remove:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # Normalize whitespace
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two channel names"""
        clean1 = self._clean_name(name1)
        clean2 = self._clean_name(name2)
        
        # Use difflib for similarity
        similarity = difflib.SequenceMatcher(None, clean1, clean2).ratio()
        
        # Boost similarity for common abbreviations
        abbreviations = {
            'espn': 'entertainment sports programming network',
            'cnn': 'cable news network',
            'bbc': 'british broadcasting corporation',
            'nbc': 'national broadcasting company',
            'abc': 'american broadcasting company',
            'cbs': 'columbia broadcasting system',
            'mtv': 'music television',
            'nat geo': 'national geographic',
            'discovery': 'disc',
            'sci fi': 'syfy'
        }
        
        for abbr, full in abbreviations.items():
            if (abbr in clean1 and full in clean2) or (full in clean1 and abbr in clean2):
                similarity = max(similarity, 0.9)
        
        return similarity
    
    def _partial_match(self, name1: str, name2: str) -> bool:
        """Check if names partially match"""
        clean1 = self._clean_name(name1)
        clean2 = self._clean_name(name2)
        
        # Split into words and check for significant word overlap
        words1 = set(clean1.split())
        words2 = set(clean2.split())
        
        # Remove common words that don't help with matching
        common_words = {'tv', 'channel', 'network', 'news', 'sports', 'the', 'and', 'of'}
        words1 -= common_words
        words2 -= common_words
        
        if not words1 or not words2:
            return False
        
        # Calculate word overlap
        overlap = len(words1.intersection(words2))
        min_words = min(len(words1), len(words2))
        
        return overlap >= max(1, min_words * 0.5)
    
    def _number_match(self, channel_number: str, epg_name: str) -> bool:
        """Check if channel number appears in EPG name"""
        # Extract numbers from both
        channel_nums = re.findall(r'\d+(?:\.\d+)?', channel_number)
        epg_nums = re.findall(r'\d+(?:\.\d+)?', epg_name)
        
        return bool(set(channel_nums).intersection(set(epg_nums)))
    
    def _icon_match(self, logo_url1: str, logo_url2: str) -> bool:
        """Check if icon URLs are similar"""
        # Extract filename without extension
        def extract_filename(url):
            import os
            filename = os.path.basename(url)
            return os.path.splitext(filename)[0].lower()
        
        file1 = extract_filename(logo_url1)
        file2 = extract_filename(logo_url2)
        
        return file1 == file2 or file1 in file2 or file2 in file1
    
    def apply_mappings(self, matches: List[ChannelMatch], update_existing: bool = True) -> int:
        """Apply the channel mappings to the database"""
        applied_count = 0
        
        for match in matches:
            channel = self.db.query(Channel).filter(Channel.id == match.channel_id).first()
            if not channel:
                continue
            
            # Only update if confidence is high or if explicitly requested
            if match.confidence >= 0.8 or (update_existing and match.confidence >= 0.6):
                old_epg_id = channel.epg_channel_id
                channel.epg_channel_id = match.epg_channel_id
                applied_count += 1
                
                logger.info(f"Applied mapping for channel '{channel.name}': "
                          f"'{old_epg_id}' -> '{match.epg_channel_id}' "
                          f"(confidence: {match.confidence:.2f})")
        
        self.db.commit()
        return applied_count
    
    def get_unmapped_channels(self) -> List[Channel]:
        """Get channels that don't have EPG mappings"""
        return self.db.query(Channel).filter(
            Channel.is_active == True,
            Channel.epg_channel_id.is_(None)
        ).all()
    
    def get_mapping_suggestions(self, epg_channels: List[EPGChannel], 
                              min_confidence: float = 0.5) -> List[ChannelMatch]:
        """Get mapping suggestions for unmapped channels"""
        unmapped_channels = self.get_unmapped_channels()
        suggestions = []
        
        for channel in unmapped_channels:
            match = self._find_best_match(channel, epg_channels)
            if match and match.confidence >= min_confidence:
                suggestions.append(match)
        
        # Sort by confidence descending
        return sorted(suggestions, key=lambda x: x.confidence, reverse=True)
    
    def validate_mappings(self) -> Dict[str, List[str]]:
        """Validate existing EPG mappings and return issues found"""
        issues = {
            'duplicate_mappings': [],
            'missing_programs': [],
            'invalid_epg_ids': []
        }
        
        # Check for duplicate EPG channel IDs
        channels = self.db.query(Channel).filter(
            Channel.is_active == True,
            Channel.epg_channel_id.isnot(None)
        ).all()
        
        epg_id_counts = {}
        for channel in channels:
            epg_id = channel.epg_channel_id
            if epg_id in epg_id_counts:
                epg_id_counts[epg_id].append(channel.name)
            else:
                epg_id_counts[epg_id] = [channel.name]
        
        for epg_id, channel_names in epg_id_counts.items():
            if len(channel_names) > 1:
                issues['duplicate_mappings'].append(f"EPG ID '{epg_id}' mapped to: {', '.join(channel_names)}")
        
        # Check for channels with no recent EPG programs
        from datetime import datetime, timedelta
        recent_date = datetime.utcnow() - timedelta(days=2)
        
        for channel in channels:
            program_count = self.db.query(EPGProgram).filter(
                EPGProgram.channel_id == channel.id,
                EPGProgram.start_time >= recent_date
            ).count()
            
            if program_count == 0:
                issues['missing_programs'].append(
                    f"Channel '{channel.name}' (EPG ID: {channel.epg_channel_id}) has no recent programs"
                )
        
        return issues