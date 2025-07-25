#!/bin/bash

# IPTV PVR Emergency Stop Script

echo "IPTV PVR Emergency Stop"
echo "======================"
echo ""

# Function to forcefully stop all IPTV PVR processes
force_stop() {
    echo "Searching for IPTV PVR processes..."
    
    # Find all processes using port 8000
    if lsof -i :8000 > /dev/null 2>&1; then
        echo "Found processes on port 8000:"
        lsof -i :8000
        PIDS=$(lsof -ti :8000)
        if [ ! -z "$PIDS" ]; then
            echo -e "\nKilling processes on port 8000..."
            kill -9 $PIDS
            echo "Killed PIDs: $PIDS"
        fi
    fi
    
    # Find all uvicorn processes
    UVICORN_PIDS=$(pgrep -f "uvicorn app.main:app")
    if [ ! -z "$UVICORN_PIDS" ]; then
        echo -e "\nFound uvicorn processes:"
        ps aux | grep "uvicorn app.main:app" | grep -v grep
        echo -e "\nKilling uvicorn processes..."
        kill -9 $UVICORN_PIDS
        echo "Killed PIDs: $UVICORN_PIDS"
    fi
    
    # Find any Python processes running main.py or app.main
    PYTHON_PIDS=$(pgrep -f "python.*app.main")
    if [ ! -z "$PYTHON_PIDS" ]; then
        echo -e "\nFound Python app processes..."
        kill -9 $PYTHON_PIDS
        echo "Killed PIDs: $PYTHON_PIDS"
    fi
    
    # Clean up any stale lock files
    if [ -f "uvicorn.pid" ]; then
        rm -f uvicorn.pid
        echo "Removed stale PID file"
    fi
    
    echo -e "\nAll IPTV PVR processes have been stopped."
}

# Check if any processes are running
if pgrep -f "uvicorn app.main:app" > /dev/null || lsof -i :8000 > /dev/null 2>&1; then
    force_stop
else
    echo "No IPTV PVR processes found running."
fi

echo -e "\nYou can now start the server with: ./run.sh"