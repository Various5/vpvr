#!/bin/bash

# HDHomeRun Manager for IPTV PVR
# Manage multiple HDHomeRun instances on different ports

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HDHR_PIDS_FILE="$SCRIPT_DIR/.hdhr_pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_MAIN_SERVER="http://localhost:8000"

show_help() {
    echo "HDHomeRun Manager for IPTV PVR"
    echo "==============================="
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  start [port]     Start HDHomeRun server on specified port (default: 5004)"
    echo "  stop [port]      Stop HDHomeRun server on specified port (stops all if no port)"
    echo "  status           Show status of all HDHomeRun instances"
    echo "  list             List all running HDHomeRun instances"
    echo "  test [port]      Test HDHomeRun endpoints on specified port"
    echo ""
    echo "Options:"
    echo "  --main-server URL    Main IPTV PVR server URL (default: $DEFAULT_MAIN_SERVER)"
    echo ""
    echo "Examples:"
    echo "  $0 start             # Start on default port 5004"
    echo "  $0 start 5005        # Start on port 5005"
    echo "  $0 start 5006 --main-server http://192.168.1.100:8000"
    echo "  $0 stop 5004         # Stop instance on port 5004"
    echo "  $0 stop              # Stop all instances"
    echo "  $0 status            # Show all running instances"
}

# Function to start HDHomeRun server
start_hdhr() {
    local port=${1:-5004}
    local main_server=${MAIN_SERVER:-$DEFAULT_MAIN_SERVER}
    
    echo -e "${BLUE}Starting HDHomeRun server on port $port...${NC}"
    
    # Check if port is already in use
    if lsof -i :$port > /dev/null 2>&1; then
        echo -e "${RED}Error: Port $port is already in use${NC}"
        return 1
    fi
    
    # Activate virtual environment
    source "$SCRIPT_DIR/venv/bin/activate"
    
    # Start the server in background
    nohup python3 "$SCRIPT_DIR/hdhr_server.py" --port $port --main-server "$main_server" > "$SCRIPT_DIR/hdhr_$port.log" 2>&1 &
    local pid=$!
    
    # Save PID
    echo "$port:$pid" >> "$HDHR_PIDS_FILE"
    
    # Wait a moment and check if it started
    sleep 2
    if kill -0 $pid 2>/dev/null; then
        echo -e "${GREEN}HDHomeRun server started successfully on port $port (PID: $pid)${NC}"
        echo -e "${GREEN}Log file: $SCRIPT_DIR/hdhr_$port.log${NC}"
        echo ""
        echo "Access URLs:"
        local ip=$(hostname -I | awk '{print $1}')
        echo "  Discovery: http://$ip:$port/discover.json"
        echo "  Device XML: http://$ip:$port/device.xml"
        echo "  Lineup: http://$ip:$port/lineup.json"
        echo ""
        echo "For Jellyfin/Plex:"
        echo "  Use: http://$ip:$port"
        return 0
    else
        echo -e "${RED}Failed to start HDHomeRun server on port $port${NC}"
        echo "Check log file: $SCRIPT_DIR/hdhr_$port.log"
        return 1
    fi
}

# Function to stop HDHomeRun server
stop_hdhr() {
    local port=$1
    
    if [ -z "$port" ]; then
        echo -e "${YELLOW}Stopping all HDHomeRun instances...${NC}"
        
        if [ -f "$HDHR_PIDS_FILE" ]; then
            while IFS=: read -r p pid; do
                if kill -0 $pid 2>/dev/null; then
                    kill $pid
                    echo -e "${GREEN}Stopped HDHomeRun on port $p (PID: $pid)${NC}"
                fi
            done < "$HDHR_PIDS_FILE"
            rm -f "$HDHR_PIDS_FILE"
        fi
        
        # Also kill any remaining hdhr_server.py processes
        pkill -f "hdhr_server.py" 2>/dev/null
    else
        echo -e "${YELLOW}Stopping HDHomeRun server on port $port...${NC}"
        
        # Find PID for specific port
        if [ -f "$HDHR_PIDS_FILE" ]; then
            local found=false
            while IFS=: read -r p pid; do
                if [ "$p" = "$port" ] && kill -0 $pid 2>/dev/null; then
                    kill $pid
                    echo -e "${GREEN}Stopped HDHomeRun on port $port (PID: $pid)${NC}"
                    found=true
                fi
            done < "$HDHR_PIDS_FILE"
            
            if [ "$found" = false ]; then
                echo -e "${YELLOW}No HDHomeRun instance found on port $port${NC}"
            fi
            
            # Clean up PID file
            grep -v "^$port:" "$HDHR_PIDS_FILE" > "$HDHR_PIDS_FILE.tmp" || true
            mv "$HDHR_PIDS_FILE.tmp" "$HDHR_PIDS_FILE" 2>/dev/null || true
        fi
    fi
}

# Function to show status
show_status() {
    echo -e "${BLUE}HDHomeRun Server Status${NC}"
    echo "======================="
    echo ""
    
    local count=0
    if [ -f "$HDHR_PIDS_FILE" ]; then
        while IFS=: read -r port pid; do
            if kill -0 $pid 2>/dev/null; then
                echo -e "Port $port: ${GREEN}Running${NC} (PID: $pid)"
                count=$((count + 1))
            else
                echo -e "Port $port: ${RED}Stopped${NC} (PID: $pid was not running)"
            fi
        done < "$HDHR_PIDS_FILE"
    fi
    
    if [ $count -eq 0 ]; then
        echo "No HDHomeRun instances are running"
    else
        echo ""
        echo "Total running instances: $count"
    fi
    
    # Clean up dead PIDs
    if [ -f "$HDHR_PIDS_FILE" ]; then
        local temp_file=$(mktemp)
        while IFS=: read -r port pid; do
            if kill -0 $pid 2>/dev/null; then
                echo "$port:$pid" >> "$temp_file"
            fi
        done < "$HDHR_PIDS_FILE"
        mv "$temp_file" "$HDHR_PIDS_FILE"
    fi
}

# Function to test HDHomeRun endpoints
test_hdhr() {
    local port=${1:-5004}
    local ip=$(hostname -I | awk '{print $1}')
    
    echo -e "${BLUE}Testing HDHomeRun endpoints on port $port${NC}"
    echo "========================================"
    echo ""
    
    echo "1. Testing discover.json:"
    curl -s "http://$ip:$port/discover.json" | python3 -m json.tool | head -10 || echo "Failed"
    echo ""
    
    echo "2. Testing lineup_status.json:"
    curl -s "http://$ip:$port/lineup_status.json" | python3 -m json.tool || echo "Failed"
    echo ""
    
    echo "3. Testing lineup.json (first 3 channels):"
    curl -s "http://$ip:$port/lineup.json" | python3 -m json.tool | head -30 || echo "Failed"
}

# Parse main server option
MAIN_SERVER=""
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --main-server)
            MAIN_SERVER="$2"
            shift 2
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done
set -- "${ARGS[@]}"

# Main command handling
case "$1" in
    start)
        start_hdhr "$2"
        ;;
    stop)
        stop_hdhr "$2"
        ;;
    status|list)
        show_status
        ;;
    test)
        test_hdhr "$2"
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac