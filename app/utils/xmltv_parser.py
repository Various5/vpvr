import httpx
from lxml import etree
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz

class XMLTVParser:
    def __init__(self):
        self.channels = {}
        self.programs = []
        
    async def parse_from_url(self, url: str) -> Dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return self.parse(response.content)
    
    def parse_from_file(self, file_path: str) -> Dict:
        with open(file_path, 'rb') as f:
            content = f.read()
        return self.parse(content)
    
    def parse(self, content: bytes) -> Dict:
        self.channels = {}
        self.programs = []
        
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Invalid XML format: {e}")
        
        # Parse channels
        for channel_elem in root.findall('.//channel'):
            channel_id = channel_elem.get('id')
            if channel_id:
                channel_info = {
                    'id': channel_id,
                    'display_names': [],
                    'icon': None
                }
                
                # Get display names
                for name_elem in channel_elem.findall('display-name'):
                    if name_elem.text:
                        channel_info['display_names'].append(name_elem.text)
                
                # Get icon
                icon_elem = channel_elem.find('icon')
                if icon_elem is not None:
                    channel_info['icon'] = icon_elem.get('src')
                
                self.channels[channel_id] = channel_info
        
        # Parse programs
        for prog_elem in root.findall('.//programme'):
            program = self._parse_programme(prog_elem)
            if program:
                self.programs.append(program)
        
        return {
            'channels': self.channels,
            'programs': self.programs
        }
    
    def _parse_programme(self, prog_elem) -> Optional[Dict]:
        channel_id = prog_elem.get('channel')
        start = prog_elem.get('start')
        stop = prog_elem.get('stop')
        
        if not all([channel_id, start, stop]):
            return None
        
        program = {
            'channel_id': channel_id,
            'start': self._parse_datetime(start),
            'stop': self._parse_datetime(stop),
            'title': '',
            'description': '',
            'category': '',
            'episode_num': '',
            'season_num': '',
            'series_id': '',
            'icon': '',
            'is_new': False,
            'is_live': False,
            'is_repeat': False
        }
        
        # Title
        title_elem = prog_elem.find('title')
        if title_elem is not None and title_elem.text:
            program['title'] = title_elem.text
        
        # Description
        desc_elem = prog_elem.find('desc')
        if desc_elem is not None and desc_elem.text:
            program['description'] = desc_elem.text
        
        # Category
        for cat_elem in prog_elem.findall('category'):
            if cat_elem.text:
                program['category'] = cat_elem.text
                break
        
        # Episode info
        episode_elem = prog_elem.find('episode-num')
        if episode_elem is not None:
            system = episode_elem.get('system', '')
            if system == 'onscreen' and episode_elem.text:
                # Parse S01E02 format
                parts = episode_elem.text.upper().split('E')
                if len(parts) == 2 and parts[0].startswith('S'):
                    program['season_num'] = parts[0][1:]
                    program['episode_num'] = parts[1]
            elif episode_elem.text:
                program['episode_num'] = episode_elem.text
        
        # Icon
        icon_elem = prog_elem.find('icon')
        if icon_elem is not None:
            program['icon'] = icon_elem.get('src', '')
        
        # Flags
        new_elem = prog_elem.find('new')
        if new_elem is not None:
            program['is_new'] = True
        
        live_elem = prog_elem.find('live')
        if live_elem is not None:
            program['is_live'] = True
        
        repeat_elem = prog_elem.find('previously-shown')
        if repeat_elem is not None:
            program['is_repeat'] = True
        
        # Series ID (if available)
        for elem in prog_elem:
            if elem.tag == 'episode-num' and elem.get('system') == 'dd_progid':
                if elem.text and elem.text.startswith('SH'):
                    program['series_id'] = elem.text
        
        return program
    
    def _parse_datetime(self, dt_string: str) -> datetime:
        # XMLTV datetime format: YYYYMMDDHHmmss +/-HHmm
        if len(dt_string) >= 14:
            dt_part = dt_string[:14]
            dt = datetime.strptime(dt_part, '%Y%m%d%H%M%S')
            
            # Handle timezone
            if len(dt_string) > 14:
                tz_string = dt_string[14:].strip()
                if tz_string.startswith(('+', '-')):
                    sign = 1 if tz_string[0] == '+' else -1
                    hours = int(tz_string[1:3])
                    minutes = int(tz_string[3:5]) if len(tz_string) >= 5 else 0
                    offset_seconds = sign * (hours * 3600 + minutes * 60)
                    tz = pytz.FixedOffset(offset_seconds // 60)
                    dt = tz.localize(dt)
                else:
                    dt = pytz.UTC.localize(dt)
            else:
                dt = pytz.UTC.localize(dt)
            
            return dt
        else:
            raise ValueError(f"Invalid datetime format: {dt_string}")
    
    def get_programs_for_channel(self, channel_id: str) -> List[Dict]:
        return [p for p in self.programs if p['channel_id'] == channel_id]
    
    def get_current_program(self, channel_id: str, now: Optional[datetime] = None) -> Optional[Dict]:
        if now is None:
            now = datetime.now(pytz.UTC)
        
        channel_programs = self.get_programs_for_channel(channel_id)
        for program in channel_programs:
            if program['start'] <= now < program['stop']:
                return program
        
        return None
    
    def get_upcoming_programs(self, channel_id: str, hours: int = 24) -> List[Dict]:
        now = datetime.now(pytz.UTC)
        future = now + timedelta(hours=hours)
        
        channel_programs = self.get_programs_for_channel(channel_id)
        return [p for p in channel_programs if p['start'] >= now and p['start'] < future]
    
    def export_channel_xmltv(self, channel_id: str) -> str:
        root = etree.Element('tv')
        
        # Add channel info
        if channel_id in self.channels:
            channel_info = self.channels[channel_id]
            channel_elem = etree.SubElement(root, 'channel', id=channel_id)
            
            for name in channel_info['display_names']:
                name_elem = etree.SubElement(channel_elem, 'display-name')
                name_elem.text = name
            
            if channel_info['icon']:
                etree.SubElement(channel_elem, 'icon', src=channel_info['icon'])
        
        # Add programs
        channel_programs = self.get_programs_for_channel(channel_id)
        for program in channel_programs:
            self._add_programme_element(root, program)
        
        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
    
    def _add_programme_element(self, parent, program: Dict):
        prog_elem = etree.SubElement(
            parent, 
            'programme',
            channel=program['channel_id'],
            start=program['start'].strftime('%Y%m%d%H%M%S %z'),
            stop=program['stop'].strftime('%Y%m%d%H%M%S %z')
        )
        
        if program['title']:
            title_elem = etree.SubElement(prog_elem, 'title')
            title_elem.text = program['title']
        
        if program['description']:
            desc_elem = etree.SubElement(prog_elem, 'desc')
            desc_elem.text = program['description']
        
        if program['category']:
            cat_elem = etree.SubElement(prog_elem, 'category')
            cat_elem.text = program['category']
        
        if program['season_num'] and program['episode_num']:
            ep_elem = etree.SubElement(prog_elem, 'episode-num', system='onscreen')
            ep_elem.text = f"S{program['season_num'].zfill(2)}E{program['episode_num'].zfill(2)}"
        
        if program['icon']:
            etree.SubElement(prog_elem, 'icon', src=program['icon'])
        
        if program['is_new']:
            etree.SubElement(prog_elem, 'new')
        
        if program['is_live']:
            etree.SubElement(prog_elem, 'live')
        
        if program['is_repeat']:
            etree.SubElement(prog_elem, 'previously-shown')