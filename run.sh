#!/bin/bash

# IPTV PVR Startup Script

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n\nShutting down IPTV PVR..."
    
    # Get the PID of the uvicorn process started by this script
    if [ ! -z "$UVICORN_PID" ]; then
        echo "Stopping server (PID: $UVICORN_PID)..."
        kill -TERM $UVICORN_PID 2>/dev/null
        
        # Give it 5 seconds to shutdown gracefully
        for i in {1..5}; do
            if ! kill -0 $UVICORN_PID 2>/dev/null; then
                echo "Server stopped gracefully."
                exit 0
            fi
            echo -n "."
            sleep 1
        done
        
        # If still running, force kill
        echo -e "\nForce stopping server..."
        kill -9 $UVICORN_PID 2>/dev/null
    fi
    
    # Also clean up any other uvicorn processes
    PIDS=$(pgrep -f "uvicorn app.main:app")
    if [ ! -z "$PIDS" ]; then
        echo "Cleaning up remaining processes..."
        kill -9 $PIDS 2>/dev/null
    fi
    
    echo "Shutdown complete."
    exit 0
}

# Set up trap to catch CTRL+C and other termination signals
trap cleanup INT TERM EXIT

echo "IPTV PVR System"
echo "==============="
echo "(Press CTRL+C to stop)"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Initialize database if needed
if [ ! -f "iptv_pvr.db" ]; then
    echo "Initializing database..."
    python init_db.py
fi

# Create recordings directory
mkdir -p recordings

# Kill any existing server processes
echo "Checking for existing server processes..."
if lsof -i :8000 > /dev/null 2>&1; then
    echo "Found existing process on port 8000, stopping it..."
    # Get PIDs using port 8000
    PIDS=$(lsof -ti :8000)
    if [ ! -z "$PIDS" ]; then
        kill -9 $PIDS
        echo "Killed process(es): $PIDS"
        sleep 2
    fi
fi

# Also check for any uvicorn processes
UVICORN_PIDS=$(pgrep -f "uvicorn app.main:app")
if [ ! -z "$UVICORN_PIDS" ]; then
    echo "Found running uvicorn process(es), stopping..."
    kill -9 $UVICORN_PIDS
    echo "Killed uvicorn process(es): $UVICORN_PIDS"
    sleep 1
fi

# Start the application
echo ""
echo "Starting IPTV PVR..."
echo "Web Interface: http://localhost:8000"
echo "HDHomeRun: http://localhost:5004"
echo ""
echo "Default login: admin / adminpass"
echo ""

# Get the actual IP address for better display
IP_ADDR=$(hostname -I | awk '{print $1}')
if [ ! -z "$IP_ADDR" ]; then
    echo "Also available at: http://$IP_ADDR:8000"
    echo ""
fi

# Inform about HDHomeRun manager
echo "HDHomeRun Server:"
echo "  To start HDHomeRun on port 5004: ./hdhr_manager.sh start"
echo "  To start on custom port: ./hdhr_manager.sh start 5005"
echo "  For more options: ./hdhr_manager.sh help"
echo ""

# Start uvicorn in the background and capture its PID
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
UVICORN_PID=$!

# Wait for the uvicorn process
wait $UVICORN_PID