      Virtual Personal Video Recorder
               for IPTV


==================================================================
Turn your IPTV (M3U playlists) into a full-featured DVR with
scheduling, EPG support, HDHomeRun emulation, live streaming,
multi-user access, and more.
==================================================================

### FEATURES

- HDHomeRun Emulation (compatible with Plex, Jellyfin, Emby, Channels DVR, NextPVR)
- Smart Recording (single episodes or full series)
- M3U / M3U8 Playlist Support
- EPG / XMLTV Integration
- Multi-User Role Management
- REST API Access
- Web-Based Live TV Streaming
- Automatic Storage Cleanup
- Dark Mode / Mobile Responsive Interface

---

### RELEASE INFO

```
Version     : v1.0.0
Date        : 2024-07-25
Platform    : Linux / Docker, Python 3.12+, Web App
License     : Open Source
```

---

### QUICK START (DOCKER)

```bash
git clone https://github.com/Various5/vpvr.git
cd vpvr
docker-compose up -d
```

Access the web interface at:  
`http://localhost:8000`  
Login credentials: `admin` / `adminpass`

---

### MANUAL INSTALLATION

```bash
git clone https://github.com/Various5/vpvr.git
cd vpvr
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python init_db.py
./run.sh
```

---

### SYSTEM REQUIREMENTS

```
Minimum:
  - 2 CPU cores
  - 2 GB RAM
  - 10 GB storage
  - Python 3.12+
  - FFmpeg

Recommended:
  - 4+ CPU cores
  - 4+ GB RAM
  - 50+ GB storage
  - FFmpeg with hardware acceleration
```

---

### CONFIGURATION

**1. Import M3U Playlist**  
Navigate to:  
`Admin → Import Manager → Add Source → Enter M3U URL`

**2. Add EPG Source (Optional)**  
Navigate to:  
`Admin → EPG Manager → Add Source → Enter XMLTV URL`

**3. Enable HDHomeRun Emulation**  
Navigate to:  
`Settings → Network → Enable HDHomeRun`

**4. Set Recording Preferences**  
Navigate to:  
`Settings → Recording`

---

### HDHOMERUN EMULATION URLS

Replace `your-ip` with the actual IP address of your server:

```
Discovery : http://your-ip:8000/discover.json
Lineup    : http://your-ip:8000/lineup.json
```

---

### REST API ENDPOINTS

```
POST   /api/auth/login
GET    /api/channels
GET    /api/epg/programs
GET    /api/recordings
POST   /api/recordings/schedule
GET    /api/stream/{channel_id}
```

---

### CREDITS

```
Author     : Various5
Tech Stack : Python, FastAPI, FFmpeg
License    : Open Source
```

---

```
NFO Generated: 2024-07-25
```