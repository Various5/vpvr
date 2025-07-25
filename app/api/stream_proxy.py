import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.channel import Channel
from app.auth.dependencies import get_current_user
from app.models.user import User
import httpx
import subprocess
import os
import tempfile
import shutil
from typing import AsyncIterator, Optional
from jose import jwt, JWTError, ExpiredSignatureError
from app.config import get_settings
from datetime import datetime
from app.auth.security import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()

async def get_current_user_flexible(
    token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Flexible authentication that accepts token from either:
    1. Authorization header (via get_current_user)
    2. Query parameter 'token'
    
    Returns None if authentication fails (for streaming endpoints to handle gracefully)
    """
    # First try the standard authentication header
    if current_user:
        return current_user
    
    # Then try the query parameter token
    if token:
        try:
            # Use the existing decode_access_token function which handles expiration
            payload = decode_access_token(token)
            if payload is None:
                logger.warning("Token decode failed - likely expired or invalid")
                return None
                
            username = payload.get("sub")
            if username is None:
                logger.warning("Token missing username (sub)")
                return None
            
            # Check if token is expired
            exp = payload.get("exp")
            if exp:
                current_time = datetime.utcnow().timestamp()
                if current_time > exp:
                    # Check if we're within the grace period for streaming
                    if current_time <= exp + settings.stream_auth_grace_period:
                        logger.info(f"Token expired but within grace period for user {username}")
                        # Continue with authentication
                    else:
                        logger.warning(f"Token expired beyond grace period for user {username}")
                        return None
            
            # Get user from database
            from app.models.user import User as UserModel
            user = db.query(UserModel).filter(UserModel.username == username).first()
            if user is None:
                logger.warning(f"User not found: {username}")
                return None
            
            if not user.is_active:
                logger.warning(f"User is inactive: {username}")
                return None
                
            return user
        except ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except JWTError as e:
            logger.warning(f"JWT validation error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in token validation: {str(e)}")
            return None
    
    # No authentication provided
    return None

async def stream_generator(stream_url: str) -> AsyncIterator[bytes]:
    """
    Simple proxy streaming without transcoding.
    For streams that are already in a compatible format.
    """
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        try:
            async with client.stream('GET', stream_url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk
        except Exception as e:
            logger.error(f"Stream proxy error: {e}")
            raise

async def transcode_stream(stream_url: str, output_format: str = "hls") -> AsyncIterator[bytes]:
    """
    Transcode stream using FFmpeg to a browser-compatible format.
    """
    # Create temporary directory for HLS segments
    temp_dir = tempfile.mkdtemp(prefix="iptv_stream_")
    
    try:
        if output_format == "hls":
            # HLS output configuration
            playlist_path = os.path.join(temp_dir, "playlist.m3u8")
            segment_pattern = os.path.join(temp_dir, "segment_%03d.ts")
            
            # FFmpeg command for HLS transcoding
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c:v', 'copy',  # Try to copy video codec if compatible
                '-c:a', 'aac',   # Transcode audio to AAC
                '-b:a', '128k',
                '-f', 'hls',
                '-hls_time', '4',
                '-hls_list_size', '6',
                '-hls_flags', 'delete_segments+append_list',
                '-hls_segment_filename', segment_pattern,
                playlist_path
            ]
        else:
            # Direct MPEG-TS streaming
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-f', 'mpegts',
                '-'
            ]
        
        # Start FFmpeg process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        if output_format == "hls":
            # Wait for initial segments to be created
            for _ in range(50):  # Wait up to 5 seconds
                if os.path.exists(playlist_path):
                    await asyncio.sleep(0.5)  # Give it time to create segments
                    break
                await asyncio.sleep(0.1)
            
            # Stream the playlist and segments
            while True:
                if os.path.exists(playlist_path):
                    with open(playlist_path, 'rb') as f:
                        yield f.read()
                await asyncio.sleep(1)
        else:
            # Stream direct output
            while True:
                chunk = await process.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
        
        # Wait for process to complete
        await process.wait()
        
    except Exception as e:
        logger.error(f"Transcoding error: {e}")
        raise
    finally:
        # Cleanup
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.get("/channels/{channel_id}/stream")
async def proxy_channel_stream(
    channel_id: int,
    transcode: bool = False,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_flexible)
):
    """
    Proxy channel stream with optional transcoding.
    
    Args:
        channel_id: The channel ID to stream
        transcode: Whether to transcode the stream (default: False)
    """
    # Check if authentication is required based on configuration
    if settings.require_auth_for_streaming and current_user is None:
        logger.warning(f"Unauthenticated access denied to channel {channel_id} stream")
        raise HTTPException(status_code=401, detail="Authentication required for streaming")
    elif current_user is None:
        # Allow streaming without authentication if not required
        logger.info(f"Unauthenticated access allowed to channel {channel_id} stream")
    
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if not channel.is_active:
        raise HTTPException(status_code=403, detail="Channel is not active")
    
    # Log the streaming attempt
    if current_user:
        logger.info(f"User {current_user.username} streaming channel {channel_id}")
    else:
        logger.info(f"Anonymous streaming channel {channel_id}")
    
    try:
        if transcode:
            # Use FFmpeg transcoding
            return StreamingResponse(
                transcode_stream(channel.stream_url, "mpegts"),
                media_type="video/mp2t",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",  # Allow CORS for video playback
                }
            )
        else:
            # Simple proxy without transcoding
            return StreamingResponse(
                stream_generator(channel.stream_url),
                media_type="application/octet-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",  # Allow CORS for video playback
                }
            )
    except Exception as e:
        logger.error(f"Stream error for channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Stream error: {str(e)}")

@router.get("/channels/{channel_id}/stream.m3u8")
async def proxy_channel_hls(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_flexible)
):
    """
    Proxy channel stream as HLS.
    This endpoint generates an HLS playlist that points to transcoded segments.
    """
    # Check if authentication is required based on configuration
    if settings.require_auth_for_streaming and current_user is None:
        logger.warning(f"Unauthenticated access denied to channel {channel_id} HLS stream")
        raise HTTPException(status_code=401, detail="Authentication required for streaming")
    elif current_user is None:
        logger.info(f"Unauthenticated access allowed to channel {channel_id} HLS stream")
    
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if not channel.is_active:
        raise HTTPException(status_code=403, detail="Channel is not active")
    
    # Generate a simple HLS playlist that points to the transcoded stream
    # In a production system, this would manage segments properly
    playlist = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.0,
/api/stream-proxy/channels/{channel_id}/stream?transcode=true
#EXT-X-ENDLIST
"""
    
    return Response(
        content=playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",  # Allow CORS for video playback
        }
    )

@router.get("/channels/v{channel_number}/stream")
async def proxy_channel_by_number_stream(
    channel_number: str,
    transcode: bool = False,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_flexible)
):
    """
    Proxy channel stream by channel number (Network Tuner format).
    
    Args:
        channel_number: The channel number to stream
        transcode: Whether to transcode the stream (default: False)
        token: Authentication token (optional)
    """
    # Check if authentication is required based on configuration
    if settings.require_auth_for_streaming and current_user is None:
        logger.warning(f"Unauthenticated access denied to channel v{channel_number} stream")
        raise HTTPException(status_code=401, detail="Authentication required for streaming")
    elif current_user is None:
        # Allow streaming without authentication if not required
        logger.info(f"Unauthenticated access allowed to channel v{channel_number} stream")
    
    # Find channel by number
    channel = db.query(Channel).filter(Channel.number == channel_number).first()
    
    if not channel:
        # Try to find by index in the channel list (Network Tuner compatibility)
        try:
            idx = int(channel_number) - 1
            channels = db.query(Channel).filter(Channel.is_active == True).order_by(Channel.number, Channel.name).all()
            if 0 <= idx < len(channels):
                channel = channels[idx]
        except ValueError:
            pass
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    if not channel.is_active:
        raise HTTPException(status_code=403, detail="Channel is not active")
    
    # Log the streaming attempt
    if current_user:
        logger.info(f"User {current_user.username} streaming channel v{channel_number} (ID: {channel.id})")
    else:
        logger.info(f"Anonymous streaming channel v{channel_number} (ID: {channel.id})")
    
    try:
        if transcode:
            # Use FFmpeg transcoding
            return StreamingResponse(
                transcode_stream(channel.stream_url, "mpegts"),
                media_type="video/mp2t",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                }
            )
        else:
            # Simple proxy without transcoding
            return StreamingResponse(
                stream_generator(channel.stream_url),
                media_type="application/octet-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                }
            )
    except Exception as e:
        logger.error(f"Stream error for channel v{channel_number}: {e}")
        raise HTTPException(status_code=500, detail=f"Stream error: {str(e)}")

@router.get("/test-ffmpeg")
async def test_ffmpeg():
    """Test if FFmpeg is available on the system."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            version_lines = result.stdout.split('\n')
            return {
                "status": "available",
                "version": version_lines[0] if version_lines else "Unknown"
            }
        else:
            return {
                "status": "error",
                "message": "FFmpeg returned non-zero exit code"
            }
    except FileNotFoundError:
        return {
            "status": "not_found",
            "message": "FFmpeg is not installed or not in PATH"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }