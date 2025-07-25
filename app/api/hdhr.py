from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.channel import Channel
from app.config import get_settings
import socket
import logging

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

def get_device_info(request: Request):
    # Get the actual server IP/hostname from the request
    base_url = str(request.base_url).rstrip('/')
    
    # If the URL contains localhost, try to get the actual IP
    if "localhost" in base_url or "127.0.0.1" in base_url:
        try:
            # Get the actual IP from the Host header first
            host_header = request.headers.get("host", "")
            if host_header and not host_header.startswith("localhost") and not host_header.startswith("127.0.0.1"):
                # Use the host from the header
                scheme = "http" if request.url.scheme == "http" else "https"
                base_url = f"{scheme}://{host_header}"
            else:
                # Try to get the server's actual IP
                hostname = socket.gethostname()
                server_ip = socket.gethostbyname(hostname)
                if server_ip and server_ip != "127.0.0.1":
                    port = request.url.port or (443 if request.url.scheme == "https" else 80)
                    if port not in [80, 443]:
                        base_url = f"{request.url.scheme}://{server_ip}:{port}"
                    else:
                        base_url = f"{request.url.scheme}://{server_ip}"
        except:
            pass  # Keep the original base_url if we can't determine the IP
    
    return {
        "FriendlyName": settings.hdhr_friendly_name,
        "Manufacturer": "IPTV PVR",
        "ManufacturerURL": "https://github.com/iptv-pvr",
        "ModelNumber": "HDTC-2US",
        "FirmwareVersion": "20230101",
        "DeviceID": settings.hdhr_device_id,
        "DeviceAuth": "iptv-pvr",
        "BaseURL": base_url,
        "LineupURL": f"{base_url}/lineup.json",
        "TunerCount": 4
    }

@router.get("/discover.json")
async def discover(request: Request):
    logger.info(f"HDHomeRun discover.json requested from {request.client.host}")
    device_info = get_device_info(request)
    logger.info(f"Returning device info with BaseURL: {device_info['BaseURL']}")
    return JSONResponse(content=device_info)

@router.get("/device.xml")
async def device_xml(request: Request):
    base_url = str(request.base_url).rstrip('/')
    device_info = get_device_info(request)
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
    <specVersion>
        <major>1</major>
        <minor>0</minor>
    </specVersion>
    <device>
        <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
        <friendlyName>{device_info['FriendlyName']}</friendlyName>
        <manufacturer>{device_info['Manufacturer']}</manufacturer>
        <manufacturerURL>{device_info['ManufacturerURL']}</manufacturerURL>
        <modelDescription>IPTV PVR HDHomeRun Emulator</modelDescription>
        <modelName>HDTC-2US</modelName>
        <modelNumber>{device_info['ModelNumber']}</modelNumber>
        <modelURL>{base_url}</modelURL>
        <serialNumber>{device_info['DeviceID']}</serialNumber>
        <UDN>uuid:{settings.hdhr_device_uuid}</UDN>
        <presentationURL>{base_url}</presentationURL>
    </device>
</root>"""
    
    return Response(content=xml_content, media_type="application/xml")

@router.get("/lineup_status.json")
async def lineup_status():
    return JSONResponse(content={
        "ScanInProgress": False,
        "ScanPossible": True,
        "Source": "IPTV",
        "SourceList": ["IPTV"]
    })

@router.get("/lineup.json")
async def lineup(request: Request, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip('/')
    channels = db.query(Channel).filter(Channel.is_active == True).order_by(Channel.number, Channel.name).all()
    
    lineup = []
    for idx, channel in enumerate(channels):
        channel_num = channel.number or str(idx + 1)
        lineup.append({
            "GuideNumber": channel_num,
            "GuideName": channel.name,
            "URL": f"{base_url}/auto/v{channel_num}",
            "HD": 1
        })
    
    return JSONResponse(content=lineup)

@router.get("/lineup.xml")
async def lineup_xml(request: Request, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip('/')
    channels = db.query(Channel).filter(Channel.is_active == True).order_by(Channel.number, Channel.name).all()
    
    xml_items = []
    for idx, channel in enumerate(channels):
        channel_num = channel.number or str(idx + 1)
        xml_items.append(f"""
        <Program>
            <GuideNumber>{channel_num}</GuideNumber>
            <GuideName>{channel.name}</GuideName>
            <URL>{base_url}/auto/v{channel_num}</URL>
        </Program>""")
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Lineup>
    {''.join(xml_items)}
</Lineup>"""
    
    return Response(content=xml_content, media_type="application/xml")

@router.get("/auto/v{channel_number}")
async def stream_channel(
    channel_number: str,
    db: Session = Depends(get_db)
):
    # Find channel by number
    channel = db.query(Channel).filter(Channel.number == channel_number).first()
    
    if not channel:
        # Try to find by index
        try:
            idx = int(channel_number) - 1
            channels = db.query(Channel).filter(Channel.is_active == True).order_by(Channel.number, Channel.name).all()
            if 0 <= idx < len(channels):
                channel = channels[idx]
        except:
            pass
    
    if not channel:
        return PlainTextResponse(content="Channel not found", status_code=404)
    
    # Import necessary modules for streaming
    from fastapi.responses import StreamingResponse
    import httpx
    from typing import AsyncIterator
    
    async def stream_generator(stream_url: str) -> AsyncIterator[bytes]:
        """Simple proxy streaming without authentication."""
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            try:
                async with client.stream('GET', stream_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Stream proxy error: {e}")
                raise
    
    # Stream the channel directly without authentication
    return StreamingResponse(
        stream_generator(channel.stream_url),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )


# SSDP Discovery endpoint (for network discovery)
@router.get("/ssdp/device-desc.xml")
async def ssdp_device_description(request: Request):
    return await device_xml(request)

@router.get("/server-info")
async def get_server_info(request: Request, db: Session = Depends(get_db)):
    """Get HDHomeRun server information for Plex/Jellyfin configuration"""
    # Get device info which now properly determines the base URL
    device_info = get_device_info(request)
    base_url = device_info["BaseURL"]
    
    # Count active channels
    active_channels = db.query(Channel).filter(Channel.is_active == True).count()
    
    return {
        "device_info": device_info,
        "server_urls": {
            "base_url": base_url,
            "discover_url": f"{base_url}/discover.json",
            "device_xml_url": f"{base_url}/device.xml",
            "lineup_url": f"{base_url}/lineup.json",
            "lineup_xml_url": f"{base_url}/lineup.xml",
            "epg_xml_url": f"{base_url}/api/epg/epg.xml"
        },
        "configuration": {
            "device_id": settings.hdhr_device_id,
            "device_uuid": settings.hdhr_device_uuid,
            "friendly_name": settings.hdhr_friendly_name,
            "tuner_count": 4,
            "active_channels": active_channels,
            "auth_required_for_streaming": settings.require_auth_for_streaming
        },
        "network": {
            "server_host": base_url.split("://")[1].split(":")[0] if "://" in base_url else base_url,
            "hdhr_port": settings.hdhr_port
        },
        "instructions": {
            "plex": f"Add this URL as a DVR device in Plex: {base_url}",
            "jellyfin": f"Add this URL as a Live TV tuner in Jellyfin: {base_url}",
            "emby": f"Add this URL as a Live TV device in Emby: {base_url}"
        }
    }