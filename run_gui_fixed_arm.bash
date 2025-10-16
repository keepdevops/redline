#!/bin/bash

# REDLINE Fixed GUI Runner for ARM64 macOS
# This script properly handles X11 forwarding for ARM64

echo "========================================"
echo "REDLINE ARM64 GUI - Fixed X11 Approach"
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

# Set up X11 forwarding properly
echo "Setting up X11 forwarding for ARM64..."

# Check if XQuartz is running
if ! pgrep -x "XQuartz" > /dev/null; then
    echo "Starting XQuartz..."
    open -a XQuartz
    sleep 5
fi

# Set DISPLAY to the correct value
export DISPLAY=:1
echo "DISPLAY set to: $DISPLAY"

# Get the X11 socket path
X11_SOCKET="/tmp/.X11-unix/X1"
if [ -S "$X11_SOCKET" ]; then
    echo "✓ X11 socket found: $X11_SOCKET"
else
    echo "❌ X11 socket not found. Trying :0..."
    export DISPLAY=:0
    X11_SOCKET="/tmp/.X11-unix/X0"
fi

# Allow X11 connections
echo "Allowing X11 connections..."
xhost +local: 2>/dev/null || echo "Warning: xhost +local: failed"
xhost +localhost 2>/dev/null || echo "Warning: xhost +localhost failed"

# Test X11 connection with a simple test
echo "Testing X11 connection..."
docker run --rm \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  redline_arm python3 -c "
import os
print(f'DISPLAY in container: {os.environ.get(\"DISPLAY\", \"Not set\")}')
import tkinter as tk
try:
    root = tk.Tk()
    root.title('X11 Test')
    root.geometry('300x200')
    label = tk.Label(root, text='X11 is working!')
    label.pack(pady=50)
    root.after(2000, root.quit)
    root.mainloop()
    print('✅ X11 test successful!')
except Exception as e:
    print(f'❌ X11 test failed: {e}')
"

if [ $? -eq 0 ]; then
    echo "✅ X11 test successful! Starting REDLINE GUI..."
    
    # Run REDLINE with GUI
    docker run --rm \
      -e DISPLAY=$DISPLAY \
      -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
      -v $(pwd):/app \
      -v $(pwd)/data:/app/data \
      redline_arm python3 /app/data_module.py
else
    echo "❌ X11 test failed. The GUI cannot be displayed."
    echo "This is a known issue with X11 forwarding on macOS ARM64."
    echo ""
    echo "Alternative options:"
    echo "1. Use the CLI version: ./run_stooq_arm.bash"
    echo "2. Use the web interface: ./run_web_gui_arm.bash"
    echo "3. Try running on an Intel Mac with: ./run_x86.bash"
fi

echo "========================================"
echo "REDLINE session completed"
