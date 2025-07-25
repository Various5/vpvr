#!/bin/bash
cd /home/devuser/VPVR/iptv_pvr
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
echo $! > server.pid
echo "Server started with PID $(cat server.pid)"