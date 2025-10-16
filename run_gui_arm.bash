#!/bin/bash

# REDLINE GUI Docker Runner for ARM64 macOS with Stooq Data Import
# This script sets up X11 forwarding and imports Stooq data

echo "========================================"
echo "REDLINE ARM64 GUI with Stooq Import"
echo "========================================"

# Copy Stooq files from Downloads to data directory
echo "Checking for Stooq files in Downloads..."

DOWNLOADS_DIR="$HOME/Downloads"
DATA_DIR="$(pwd)/data"
STOOQ_DIR="$DATA_DIR/stooq_import"

# Create stooq_import directory if it doesn't exist
mkdir -p "$STOOQ_DIR"

# Check for and copy TXT files
if ls "$DOWNLOADS_DIR"/*.txt 1> /dev/null 2>&1; then
    echo "Found TXT files. Copying..."
    cp "$DOWNLOADS_DIR"/*.txt "$STOOQ_DIR/"
    TXT_COUNT=$(ls "$STOOQ_DIR"/*.txt 2>/dev/null | wc -l)
    echo "✓ Copied $TXT_COUNT TXT files to $STOOQ_DIR"
fi

# Check for and extract ZIP files
if ls "$DOWNLOADS_DIR"/*.zip 1> /dev/null 2>&1; then
    echo "Found ZIP files. Extracting..."
    for zipfile in "$DOWNLOADS_DIR"/*.zip; do
        echo "Extracting: $(basename "$zipfile")"
        unzip -o "$zipfile" -d "$STOOQ_DIR/"
    done
    echo "✓ ZIP files extracted to $STOOQ_DIR"
fi

# Count total Stooq files ready for processing
TOTAL_FILES=$(find "$STOOQ_DIR" -type f -name "*.txt" 2>/dev/null | wc -l)
if [ "$TOTAL_FILES" -gt 0 ]; then
    echo "✓ Total Stooq TXT files ready: $TOTAL_FILES"
else
    echo "ℹ No Stooq files found in Downloads"
fi

echo "========================================"

echo "Setting up X11 forwarding for REDLINE GUI..."

# Get local IP address
LOCAL_IP=$(ifconfig en0 | grep inet | grep -v inet6 | awk '{print $2}')
echo "Local IP: $LOCAL_IP"

# Start XQuartz if not running
if ! pgrep -x "XQuartz" > /dev/null; then
    echo "Starting XQuartz..."
    open -a XQuartz
    sleep 8  # Wait for XQuartz to start
fi

# Try different DISPLAY options
echo "Testing X11 display options..."

# Test if :0 works
if xset -display :0 q &>/dev/null; then
    export DISPLAY=:0
    echo "✓ Using DISPLAY=:0"
elif xset -display localhost:0 q &>/dev/null; then
    export DISPLAY=localhost:0
    echo "✓ Using DISPLAY=localhost:0"
elif xset -display $LOCAL_IP:0 q &>/dev/null; then
    export DISPLAY=$LOCAL_IP:0
    echo "✓ Using DISPLAY=$LOCAL_IP:0"
else
    export DISPLAY=localhost:0
    echo "⚠ Using default DISPLAY=localhost:0"
fi

# Allow X11 connections
echo "Allowing X11 connections..."
xhost +local: 2>/dev/null || echo "Warning: xhost +local: failed"
xhost +localhost 2>/dev/null || echo "Warning: xhost +localhost failed"
xhost +$LOCAL_IP 2>/dev/null || echo "Warning: xhost +$LOCAL_IP failed"

# Add xauth entry
echo "Setting up X11 authentication..."
xauth add $DISPLAY . $(openssl rand -hex 16 2>/dev/null || echo "f8c37ea64e4472075d27d39caa0f2186") 2>/dev/null || echo "Warning: xauth add failed"

echo "========================================"
echo "Starting REDLINE ARM64 container with GUI..."

# Run Docker container with comprehensive X11 forwarding
docker run -it --rm \
    -e DISPLAY=$DISPLAY \
    -e DISPLAY=localhost:0 \
    -e DISPLAY=$LOCAL_IP:0 \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v $HOME/.Xauthority:/root/.Xauthority:ro \
    -v $(pwd)/data:/app/data \
    -v $(pwd):/app/host \
    --name redline_gui_arm \
    redline_arm \
    python3 /app/host/data_module.py

echo "========================================"
echo "REDLINE GUI session ended."

# Clean up X11 permissions
echo "Cleaning up X11 permissions..."
xhost -local: 2>/dev/null || echo "Warning: xhost -local: failed"
xhost -localhost 2>/dev/null || echo "Warning: xhost -localhost failed"
xhost -$LOCAL_IP 2>/dev/null || echo "Warning: xhost -$LOCAL_IP failed"

echo "Done!"
