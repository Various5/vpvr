VPVR - Virtual Personal Video Recorder for IPTV

TL;DR:
Turn IPTV (M3U playlists) into a DVR with scheduling, EPG support, HDHomeRun emulation, live streaming, and more.

Features:
- HDHomeRun Emulation (Plex, Jellyfin, Emby, Channels DVR, NextPVR)
- Smart Recording (single episode or series)
- M3U/M3U8 Playlist Support
- EPG/XMLTV Integration
- Multi-User Roles & REST API Access
- Web-based Live TV Streaming
- Auto Storage Cleanup
- Dark Mode & Mobile Responsive UI

Release Info:
Version: v1.0.0 | Date: 2024-07-25
Platform: Linux/Docker, Python 3.12+, Web App, Open Source

Quick Start (Docker):
git clone https://github.com/Various5/vpvr.git
cd vpvr
docker-compose up -d
Access: http://localhost:8000 (admin/adminpass)

Manual Install:
git clone https://github.com/Various5/vpvr.git
cd vpvr
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python init_db.py
./run.sh

System Requirements:
Min: 2 CPU cores, 2GB RAM, 10GB+ storage, Python 3.12+, FFmpeg
Rec: 4+ CPU, 4GB+ RAM, 50GB+ storage, FFmpeg + HW acceleration

Configuration:
1) Import M3U playlist: Admin → Import Manager → Add Source → M3U URL
2) Add EPG XMLTV (optional): Admin → EPG Manager → Add Source → XMLTV URL
3) Enable HDHomeRun Emulation: Settings → Network → Enable HDHomeRun
4) Set recording preferences: Settings → Recording

HDHomeRun Emulation URLs (replace your-ip):
- Discovery: http://your-ip:8000/discover.json
- Lineup: http://your-ip:8000/lineup.json

API Endpoints:
POST /api/auth/login
GET /api/channels
GET /api/epg/programs
GET /api/recordings
POST /api/recordings/schedule
GET /api/stream/{channel_id}

Troubleshooting:
- Channels not loading? Check M3U URL accessibility.
- Missing EPG? Verify XMLTV URL and update manually.
- Recordings fail? Check FFmpeg install and storage permissions.
- HDHomeRun not detected? Ensure port 8000 firewall is open.

Credits & License:
Code by Various5 | Powered by Python, FastAPI, FFmpeg | Open Source

NFO Generated: 2024-07-25
