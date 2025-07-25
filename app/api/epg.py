from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import get_db
from app.models.epg import EPGProgram
from app.models.channel import Channel
from app.models.epg_source import EPGSource
from app.auth.dependencies import get_current_user, require_admin
from app.utils.xmltv_parser import XMLTVParser
from pydantic import BaseModel
import pytz

router = APIRouter()

class EPGProgramResponse(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    category: Optional[str]
    episode_num: Optional[str]
    season_num: Optional[str]
    series_id: Optional[str]
    icon_url: Optional[str]
    is_new: bool
    is_live: bool
    is_repeat: bool
    
    class Config:
        from_attributes = True

class EPGImport(BaseModel):
    url: str
    update_interval: int = 21600  # 6 hours

class EPGSourceCreate(BaseModel):
    name: str
    url: str
    playlist_id: Optional[int] = None

class EPGSourceResponse(BaseModel):
    id: int
    name: str
    url: str
    playlist_id: Optional[int]
    last_updated: Optional[datetime]
    
    class Config:
        from_attributes = True

@router.get("/programs", response_model=List[EPGProgramResponse])
async def get_epg_programs(
    channel_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(EPGProgram).join(Channel)
    
    if channel_id:
        query = query.filter(EPGProgram.channel_id == channel_id)
    
    if start_time:
        query = query.filter(EPGProgram.end_time >= start_time)
    
    if end_time:
        query = query.filter(EPGProgram.start_time <= end_time)
    
    if search:
        query = query.filter(EPGProgram.title.ilike(f"%{search}%"))
    
    if category:
        query = query.filter(EPGProgram.category == category)
    
    programs = query.order_by(EPGProgram.start_time).offset(skip).limit(limit).all()
    
    return [
        EPGProgramResponse(
            id=p.id,
            channel_id=p.channel_id,
            channel_name=p.channel.name,
            title=p.title,
            description=p.description,
            start_time=p.start_time,
            end_time=p.end_time,
            category=p.category,
            episode_num=p.episode_num,
            season_num=p.season_num,
            series_id=p.series_id,
            icon_url=p.icon_url,
            is_new=p.is_new,
            is_live=p.is_live,
            is_repeat=p.is_repeat
        )
        for p in programs
    ]

@router.get("/now-next/{channel_id}")
async def get_now_next(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    now = datetime.now(pytz.UTC)
    
    # Get current program
    current = db.query(EPGProgram).filter(
        and_(
            EPGProgram.channel_id == channel_id,
            EPGProgram.start_time <= now,
            EPGProgram.end_time > now
        )
    ).first()
    
    # Get next program
    next_program = None
    if current:
        next_program = db.query(EPGProgram).filter(
            and_(
                EPGProgram.channel_id == channel_id,
                EPGProgram.start_time >= current.end_time
            )
        ).order_by(EPGProgram.start_time).first()
    
    return {
        "now": EPGProgramResponse(
            id=current.id,
            channel_id=current.channel_id,
            channel_name=current.channel.name,
            title=current.title,
            description=current.description,
            start_time=current.start_time,
            end_time=current.end_time,
            category=current.category,
            episode_num=current.episode_num,
            season_num=current.season_num,
            series_id=current.series_id,
            icon_url=current.icon_url,
            is_new=current.is_new,
            is_live=current.is_live,
            is_repeat=current.is_repeat
        ) if current else None,
        "next": EPGProgramResponse(
            id=next_program.id,
            channel_id=next_program.channel_id,
            channel_name=next_program.channel.name,
            title=next_program.title,
            description=next_program.description,
            start_time=next_program.start_time,
            end_time=next_program.end_time,
            category=next_program.category,
            episode_num=next_program.episode_num,
            season_num=next_program.season_num,
            series_id=next_program.series_id,
            icon_url=next_program.icon_url,
            is_new=next_program.is_new,
            is_live=next_program.is_live,
            is_repeat=next_program.is_repeat
        ) if next_program else None
    }

@router.post("/import")
async def import_epg(
    epg_data: EPGImport,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    background_tasks.add_task(import_epg_data, epg_data.url, db)
    return {"message": "EPG import started"}

async def import_epg_data(url: str, db: Session):
    parser = XMLTVParser()
    try:
        epg_data = await parser.parse_from_url(url)
        
        # Clear old EPG data (older than 1 day)
        cutoff_date = datetime.now(pytz.UTC) - timedelta(days=1)
        db.query(EPGProgram).filter(EPGProgram.end_time < cutoff_date).delete()
        
        # Match channels and import programs
        channels = db.query(Channel).all()
        channel_map = {ch.epg_channel_id: ch.id for ch in channels if ch.epg_channel_id}
        
        for program_data in epg_data['programs']:
            epg_channel_id = program_data['channel_id']
            
            if epg_channel_id in channel_map:
                # Check if program already exists
                existing = db.query(EPGProgram).filter(
                    and_(
                        EPGProgram.channel_id == channel_map[epg_channel_id],
                        EPGProgram.start_time == program_data['start'],
                        EPGProgram.end_time == program_data['stop']
                    )
                ).first()
                
                if not existing:
                    program = EPGProgram(
                        channel_id=channel_map[epg_channel_id],
                        title=program_data['title'],
                        description=program_data['description'],
                        start_time=program_data['start'],
                        end_time=program_data['stop'],
                        category=program_data['category'],
                        episode_num=program_data['episode_num'],
                        season_num=program_data['season_num'],
                        series_id=program_data['series_id'],
                        icon_url=program_data['icon'],
                        is_new=program_data['is_new'],
                        is_live=program_data['is_live'],
                        is_repeat=program_data['is_repeat']
                    )
                    db.add(program)
        
        db.commit()
        
    except Exception as e:
        print(f"Error importing EPG: {e}")

@router.get("/epg.xml")
async def export_all_epg(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Export EPG data for all channels in XMLTV format"""
    from fastapi.responses import Response
    
    # Get all active channels with EPG data
    channels = db.query(Channel).filter(Channel.is_active == True).all()
    
    # Start building XMLTV
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<!DOCTYPE tv SYSTEM "xmltv.dtd">')
    xml_lines.append('<tv source-info-name="IPTV PVR" generator-info-name="IPTV PVR">')
    
    # Add channels
    for channel in channels:
        channel_id = channel.epg_channel_id or f"channel-{channel.id}"
        xml_lines.append(f'  <channel id="{channel_id}">')
        xml_lines.append(f'    <display-name>{channel.name}</display-name>')
        if channel.number:
            xml_lines.append(f'    <display-name>{channel.number}</display-name>')
        if channel.logo_url:
            xml_lines.append(f'    <icon src="{channel.logo_url}"/>')
        xml_lines.append('  </channel>')
    
    # Get programs for next N days
    start_time = datetime.now(pytz.UTC)
    end_time = start_time + timedelta(days=days)
    
    programs = db.query(EPGProgram).join(Channel).filter(
        and_(
            Channel.is_active == True,
            EPGProgram.start_time >= start_time,
            EPGProgram.end_time <= end_time
        )
    ).order_by(EPGProgram.start_time).all()
    
    # Add programs
    for program in programs:
        channel_id = program.channel.epg_channel_id or f"channel-{program.channel.id}"
        start_str = program.start_time.strftime('%Y%m%d%H%M%S %z')
        end_str = program.end_time.strftime('%Y%m%d%H%M%S %z')
        
        xml_lines.append(f'  <programme start="{start_str}" stop="{end_str}" channel="{channel_id}">')
        xml_lines.append(f'    <title>{escape_xml(program.title)}</title>')
        
        if program.description:
            xml_lines.append(f'    <desc>{escape_xml(program.description)}</desc>')
        
        if program.category:
            xml_lines.append(f'    <category>{escape_xml(program.category)}</category>')
        
        if program.icon_url:
            xml_lines.append(f'    <icon src="{program.icon_url}"/>')
        
        # Episode info
        if program.series_id or program.season_num or program.episode_num:
            xmltv_ns = []
            if program.season_num:
                xmltv_ns.append(str(int(program.season_num) - 1))
            else:
                xmltv_ns.append('')
            xmltv_ns.append('.')
            if program.episode_num:
                xmltv_ns.append(str(int(program.episode_num) - 1))
            else:
                xmltv_ns.append('')
            xml_lines.append(f'    <episode-num system="xmltv_ns">{"".join(xmltv_ns)}</episode-num>')
        
        if program.is_new:
            xml_lines.append('    <new/>')
        
        if program.is_repeat:
            xml_lines.append('    <previously-shown/>')
        
        if program.is_live:
            xml_lines.append('    <live/>')
        
        xml_lines.append('  </programme>')
    
    xml_lines.append('</tv>')
    
    xml_content = '\n'.join(xml_lines)
    
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"inline; filename=epg.xml"
        }
    )

def escape_xml(text):
    """Escape special XML characters"""
    if not text:
        return ''
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')

@router.get("/channel/{channel_id}/xmltv")
async def export_channel_epg(
    channel_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Get programs for the channel
    start_time = datetime.now(pytz.UTC)
    end_time = start_time + timedelta(days=days)
    
    programs = db.query(EPGProgram).filter(
        and_(
            EPGProgram.channel_id == channel_id,
            EPGProgram.start_time >= start_time,
            EPGProgram.start_time <= end_time
        )
    ).order_by(EPGProgram.start_time).all()
    
    # Build XMLTV
    parser = XMLTVParser()
    parser.channels[channel.epg_channel_id or channel.channel_id] = {
        'id': channel.epg_channel_id or channel.channel_id,
        'display_names': [channel.name],
        'icon': channel.logo_url
    }
    
    for program in programs:
        parser.programs.append({
            'channel_id': channel.epg_channel_id or channel.channel_id,
            'start': program.start_time,
            'stop': program.end_time,
            'title': program.title,
            'description': program.description,
            'category': program.category,
            'episode_num': program.episode_num,
            'season_num': program.season_num,
            'series_id': program.series_id,
            'icon': program.icon_url,
            'is_new': program.is_new,
            'is_live': program.is_live,
            'is_repeat': program.is_repeat
        })
    
    xmltv_content = parser.export_channel_xmltv(channel.epg_channel_id or channel.channel_id)
    
    from fastapi.responses import Response
    return Response(content=xmltv_content, media_type="application/xml")

@router.post("/upload")
async def upload_epg(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    # Validate file type
    if not file.filename.endswith(('.xml', '.gz')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .xml and .gz files are allowed"
        )
    
    # Read file content
    content = await file.read()
    
    # Handle gzipped files
    if file.filename.endswith('.gz'):
        import gzip
        try:
            content = gzip.decompress(content)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to decompress gzip file: {str(e)}"
            )
    
    # Save to temporary file
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    # Import EPG data in background
    background_tasks.add_task(import_epg_from_file, tmp_path, db)
    
    return {"message": "EPG upload started"}

async def import_epg_from_file(file_path: str, db: Session):
    parser = XMLTVParser()
    try:
        epg_data = parser.parse_from_file(file_path)
        
        # Clear old EPG data (older than 1 day)
        cutoff_date = datetime.now(pytz.UTC) - timedelta(days=1)
        db.query(EPGProgram).filter(EPGProgram.end_time < cutoff_date).delete()
        
        # Match channels and import programs
        channels = db.query(Channel).all()
        channel_map = {ch.epg_channel_id: ch.id for ch in channels if ch.epg_channel_id}
        
        for program_data in epg_data['programs']:
            epg_channel_id = program_data['channel_id']
            
            if epg_channel_id in channel_map:
                # Check if program already exists
                existing = db.query(EPGProgram).filter(
                    and_(
                        EPGProgram.channel_id == channel_map[epg_channel_id],
                        EPGProgram.start_time == program_data['start'],
                        EPGProgram.end_time == program_data['stop']
                    )
                ).first()
                
                if not existing:
                    program = EPGProgram(
                        channel_id=channel_map[epg_channel_id],
                        title=program_data['title'],
                        description=program_data['description'],
                        start_time=program_data['start'],
                        end_time=program_data['stop'],
                        category=program_data['category'],
                        episode_num=program_data['episode_num'],
                        season_num=program_data['season_num'],
                        series_id=program_data['series_id'],
                        icon_url=program_data['icon'],
                        is_new=program_data['is_new'],
                        is_live=program_data['is_live'],
                        is_repeat=program_data['is_repeat']
                    )
                    db.add(program)
        
        db.commit()
        
    except Exception as e:
        print(f"Error importing EPG from file: {e}")
    finally:
        # Clean up temporary file
        import os
        if os.path.exists(file_path):
            os.remove(file_path)

# EPG Sources endpoints
@router.get("/sources", response_model=List[EPGSourceResponse])
async def get_epg_sources(
    playlist_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(EPGSource)
    if playlist_id:
        query = query.filter(EPGSource.playlist_id == playlist_id)
    return query.all()

@router.post("/sources", response_model=EPGSourceResponse)
async def create_epg_source(
    source_data: EPGSourceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    epg_source = EPGSource(
        name=source_data.name,
        url=source_data.url,
        playlist_id=source_data.playlist_id
    )
    db.add(epg_source)
    db.commit()
    db.refresh(epg_source)
    return epg_source

@router.post("/sources/{source_id}/refresh")
async def refresh_epg_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="EPG source not found")
    
    background_tasks.add_task(import_epg_data, source.url, db)
    
    # Update last_updated timestamp
    source.last_updated = datetime.utcnow()
    db.commit()
    
    return {"message": "EPG refresh started"}

@router.delete("/sources/{source_id}")
async def delete_epg_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="EPG source not found")
    
    db.delete(source)
    db.commit()
    
    return {"message": "EPG source deleted"}

@router.post("/sources/{source_id}/update")
async def update_epg_source_manually(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Manually trigger an EPG source update"""
    source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="EPG source not found")
    
    # Generate import ID
    import time
    import_id = f"epg_{source_id}_{int(time.time())}"
    
    # Start import in background with websocket updates
    from app.api.websocket import send_import_update
    background_tasks.add_task(
        import_epg_data_with_progress, 
        source.url, 
        db, 
        import_id,
        source.id
    )
    
    return {
        "message": "EPG update started",
        "import_id": import_id
    }

async def import_epg_data_with_progress(url: str, db: Session, import_id: str, source_id: int):
    """Import EPG data with progress updates"""
    from app.api.websocket import send_import_update
    parser = XMLTVParser()
    
    try:
        # Send initial progress
        await send_import_update(import_id, {
            "status": "downloading",
            "progress": 0,
            "message": "Downloading EPG data..."
        })
        
        epg_data = await parser.parse_from_url(url)
        
        # Send parsing progress
        await send_import_update(import_id, {
            "status": "parsing",
            "progress": 30,
            "message": f"Parsing {len(epg_data.get('programs', []))} programs..."
        })
        
        # Clear old EPG data (older than 1 day)
        cutoff_date = datetime.now(pytz.UTC) - timedelta(days=1)
        db.query(EPGProgram).filter(EPGProgram.end_time < cutoff_date).delete()
        
        # Match channels and import programs
        channels = db.query(Channel).all()
        channel_map = {ch.epg_channel_id: ch.id for ch in channels if ch.epg_channel_id}
        
        programs = epg_data.get('programs', [])
        total_programs = len(programs)
        imported_count = 0
        
        for i, program_data in enumerate(programs):
            epg_channel_id = program_data['channel_id']
            
            if epg_channel_id in channel_map:
                # Check if program already exists
                existing = db.query(EPGProgram).filter(
                    and_(
                        EPGProgram.channel_id == channel_map[epg_channel_id],
                        EPGProgram.start_time == program_data['start'],
                        EPGProgram.end_time == program_data['stop']
                    )
                ).first()
                
                if not existing:
                    program = EPGProgram(
                        channel_id=channel_map[epg_channel_id],
                        title=program_data['title'],
                        description=program_data['description'],
                        start_time=program_data['start'],
                        end_time=program_data['stop'],
                        category=program_data['category'],
                        episode_num=program_data['episode_num'],
                        season_num=program_data['season_num'],
                        series_id=program_data['series_id'],
                        icon_url=program_data['icon'],
                        is_new=program_data['is_new'],
                        is_live=program_data['is_live'],
                        is_repeat=program_data['is_repeat']
                    )
                    db.add(program)
                    imported_count += 1
            
            # Send progress update every 100 programs
            if i % 100 == 0:
                progress = 30 + int((i / total_programs) * 60)
                await send_import_update(import_id, {
                    "status": "importing",
                    "progress": progress,
                    "message": f"Importing programs: {i}/{total_programs}"
                })
        
        db.commit()
        
        # Update source last_updated timestamp
        source = db.query(EPGSource).filter(EPGSource.id == source_id).first()
        if source:
            source.last_updated = datetime.utcnow()
            db.commit()
        
        # Send completion
        await send_import_update(import_id, {
            "status": "completed",
            "progress": 100,
            "message": f"Successfully imported {imported_count} programs"
        })
        
    except Exception as e:
        print(f"Error importing EPG: {e}")
        await send_import_update(import_id, {
            "status": "failed",
            "progress": 0,
            "message": f"Error: {str(e)}"
        })