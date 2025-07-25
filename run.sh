#!/bin/bash

# IPTV PVR Enhanced Startup Script
# Features: Auto-start, status monitoring, colorful output, wallpaper management

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
APP_NAME="IPTV PVR System"
APP_PORT=8000
TUNER_PORT=5004
PID_FILE="/tmp/iptv_pvr.pid"
LOG_FILE="iptv_pvr.log"

# Function to print colored text
print_color() {
    echo -e "${2}${1}${NC}"
}

# Function to print header
print_header() {
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}          ${BOLD}${GREEN}IPTV PVR System Starting Up${NC}                     ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                    ${YELLOW}Version 2026.1${NC}                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Function to rename wallpapers with uniform names
rename_wallpapers() {
    print_color "🖼️  Organizing theme wallpapers..." "$CYAN"
    
    THEMES_DIR="/home/devuser/VPVR/iptv_pvr/app/static/images/themes"
    
    # Define theme mappings
    declare -A THEME_NAMES=(
        ["light"]="light"
        ["dark"]="dark"
        ["trip"]="trip"
        ["spacewars"]="spacewars"
        ["jungle"]="jungle"
        ["desert"]="desert"
        ["tech"]="tech"
    )
    
    # Process each theme directory
    for theme_dir in "$THEMES_DIR"/*; do
        if [ -d "$theme_dir" ]; then
            theme_name=$(basename "$theme_dir")
            
            # Skip if not a recognized theme
            if [ -z "${THEME_NAMES[$theme_name]}" ]; then
                continue
            fi
            
            print_color "  Processing ${theme_name} theme..." "$YELLOW"
            
            # Create temporary directory for renamed files
            temp_dir="${theme_dir}_temp"
            mkdir -p "$temp_dir"
            
            # Counter for naming
            counter=1
            
            # Find all image files and rename them
            for ext in jpg jpeg png webp JPG JPEG PNG WEBP; do
                for img in "$theme_dir"/*.$ext; do
                    if [ -f "$img" ]; then
                        # Normalize extension to lowercase
                        norm_ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
                        
                        # Create new filename
                        new_name="${THEME_NAMES[$theme_name]}${counter}.${norm_ext}"
                        
                        # Copy to temp directory with new name
                        cp "$img" "$temp_dir/$new_name"
                        
                        print_color "    ✓ Renamed $(basename "$img") → $new_name" "$GREEN"
                        
                        ((counter++))
                    fi
                done
            done
            
            # If we renamed any files, replace the original directory
            if [ "$(ls -A "$temp_dir" 2>/dev/null)" ]; then
                # Remove old files
                for ext in jpg jpeg png webp JPG JPEG PNG WEBP; do
                    rm -f "$theme_dir"/*.$ext 2>/dev/null
                done
                
                # Move renamed files back
                mv "$temp_dir"/* "$theme_dir"/ 2>/dev/null
                
                print_color "    ✓ ${theme_name} theme: $((counter-1)) wallpapers organized" "$GREEN"
            fi
            
            # Clean up temp directory
            rmdir "$temp_dir" 2>/dev/null
        fi
    done
    
    print_color "✅ Wallpaper organization complete!" "$GREEN"
}

# Function to check dependencies
check_dependencies() {
    print_color "\n📋 Checking dependencies..." "$CYAN"
    
    # Check Python
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        print_color "  ✓ Python: $PYTHON_VERSION" "$GREEN"
    else
        print_color "  ✗ Python3 not found!" "$RED"
        return 1
    fi
    
    # Check pip
    if command -v pip3 >/dev/null 2>&1; then
        print_color "  ✓ pip3 installed" "$GREEN"
    else
        print_color "  ✗ pip3 not found!" "$RED"
        return 1
    fi
    
    # Check virtual environment
    if [ -d "venv" ]; then
        print_color "  ✓ Virtual environment exists" "$GREEN"
    else
        print_color "  ⚠ Virtual environment not found (will be created)" "$YELLOW"
    fi
    
    # Check database
    if [ -f "iptv_pvr.db" ]; then
        print_color "  ✓ Database exists" "$GREEN"
    else
        print_color "  ⚠ Database not found (will be initialized)" "$YELLOW"
    fi
    
    return 0
}

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n\n${YELLOW}Shutting down IPTV PVR...${NC}"
    
    # Get the PID of the uvicorn process started by this script
    if [ ! -z "$UVICORN_PID" ]; then
        echo "Stopping server (PID: $UVICORN_PID)..."
        kill -TERM $UVICORN_PID 2>/dev/null
        
        # Give it 5 seconds to shutdown gracefully
        for i in {1..5}; do
            if ! kill -0 $UVICORN_PID 2>/dev/null; then
                print_color "✅ Server stopped gracefully." "$GREEN"
                rm -f $PID_FILE
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
    
    rm -f $PID_FILE
    print_color "Shutdown complete." "$GREEN"
    exit 0
}

# Function to display real-time status
display_status() {
    if [ ! -z "$UVICORN_PID" ] && kill -0 $UVICORN_PID 2>/dev/null; then
        # Get CPU and RAM usage for the process
        if command -v ps >/dev/null 2>&1; then
            CPU_MEM=$(ps -p $UVICORN_PID -o %cpu,%mem | tail -1)
            CPU=$(echo $CPU_MEM | awk '{print $1}')
            MEM=$(echo $CPU_MEM | awk '{print $2}')
        else
            CPU="N/A"
            MEM="N/A"
        fi
        
        print_color "\n📊 System Status:" "$CYAN"
        print_color "  ● Status: ${GREEN}RUNNING${NC}" "$BOLD"
        print_color "  PID: $UVICORN_PID" "$WHITE"
        print_color "  CPU Usage: ${CPU}%" "$CYAN"
        print_color "  RAM Usage: ${MEM}%" "$CYAN"
    fi
}

# Set up trap to catch CTRL+C and other termination signals
trap cleanup INT TERM EXIT

# Main execution
clear
print_header

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    print_color "\n⚠️  Application is already running!" "$YELLOW"
    print_color "PID: $(cat $PID_FILE)" "$WHITE"
    print_color "\nTo stop it, run: kill $(cat $PID_FILE)" "$CYAN"
    exit 1
fi

# Check dependencies
if ! check_dependencies; then
    print_color "\n❌ Dependency check failed!" "$RED"
    exit 1
fi

# Rename wallpapers for uniform naming
rename_wallpapers

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    print_color "\n📦 Creating virtual environment..." "$YELLOW"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
print_color "\n📦 Installing dependencies..." "$YELLOW"
pip install -q -r requirements.txt 2>>$LOG_FILE

# Initialize database if needed
if [ ! -f "iptv_pvr.db" ]; then
    print_color "\n🗄️  Initializing database..." "$YELLOW"
    python init_db.py 2>>$LOG_FILE
fi

# Create necessary directories
mkdir -p recordings
mkdir -p logs

# Kill any existing processes on the port
if lsof -i :$APP_PORT >/dev/null 2>&1; then
    print_color "\n⚠️  Found process on port $APP_PORT, stopping it..." "$YELLOW"
    PIDS=$(lsof -ti :$APP_PORT)
    if [ ! -z "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
        sleep 2
    fi
fi

# Start the application
print_color "\n✨ Starting web server..." "$GREEN"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"

# Start uvicorn and capture its PID
uvicorn app.main:app --host 0.0.0.0 --port $APP_PORT --reload &
UVICORN_PID=$!

# Save PID
echo $UVICORN_PID > $PID_FILE

# Wait a moment to check if it started successfully
sleep 3

if kill -0 $UVICORN_PID 2>/dev/null; then
    print_color "\n✅ $APP_NAME started successfully!" "$GREEN"
    
    # Display status
    display_status
    
    print_color "\n📌 Access Information:" "$CYAN"
    print_color "  Web Interface: ${GREEN}http://localhost:$APP_PORT${NC}" "$WHITE"
    
    IP_ADDR=$(hostname -I | awk '{print $1}')
    if [ ! -z "$IP_ADDR" ]; then
        print_color "  Network Access: ${GREEN}http://$IP_ADDR:$APP_PORT${NC}" "$WHITE"
    fi
    
    print_color "\n  Default login: ${YELLOW}admin / adminpass${NC}" "$WHITE"
    print_color "\n💡 Tip: Type 'void' anywhere in the web interface for an epic surprise! 🌌" "$PURPLE"
    
    print_color "\n${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    print_color "${YELLOW}Press CTRL+C to stop the server${NC}" "$BOLD"
    print_color "${CYAN}═══════════════════════════════════════════════════════════════${NC}\n"
    
    # Wait for the uvicorn process
    wait $UVICORN_PID
else
    print_color "\n❌ Failed to start $APP_NAME!" "$RED"
    print_color "Check $LOG_FILE for errors" "$YELLOW"
    rm -f $PID_FILE
    exit 1
fi