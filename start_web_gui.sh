#!/bin/bash

# REDLINE Web GUI Launcher for M3 Silicon Mac
# This script starts the web-based GUI that works around X11 and macOS version issues

echo "========================================"
echo "🚀 REDLINE Web GUI Launcher"
echo "========================================"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python3."
    exit 1
fi

# Check if Docker is running
if ! docker ps &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Check if ARM64 container exists
if ! docker image inspect redline_arm &> /dev/null; then
    echo "❌ ARM64 container 'redline_arm' not found."
    echo "Please run: ./build_arm.bash"
    exit 1
fi

echo "✅ Python3 available"
echo "✅ Docker running"
echo "✅ ARM64 container ready"
echo ""

# Copy Stooq files from Downloads
echo "📊 Checking for Stooq files in Downloads..."
DOWNLOADS_DIR="$HOME/Downloads"
DATA_DIR="$(pwd)/data"
STOOQ_DIR="$DATA_DIR/stooq_import"

mkdir -p "$STOOQ_DIR"

if ls "$DOWNLOADS_DIR"/*.txt 1> /dev/null 2>&1; then
    echo "Found TXT files. Copying..."
    cp "$DOWNLOADS_DIR"/*.txt "$STOOQ_DIR/"
    TXT_COUNT=$(ls "$STOOQ_DIR"/*.txt 2>/dev/null | wc -l)
    echo "✓ Copied $TXT_COUNT TXT files to $STOOQ_DIR"
fi

if ls "$DOWNLOADS_DIR"/*.zip 1> /dev/null 2>&1; then
    echo "Found ZIP files. Extracting..."
    for zipfile in "$DOWNLOADS_DIR"/*.zip; do
        echo "Extracting: $(basename "$zipfile")"
        unzip -o "$zipfile" -d "$STOOQ_DIR/"
    done
    echo "✓ ZIP files extracted to $STOOQ_DIR"
fi

TOTAL_FILES=$(find "$STOOQ_DIR" -type f -name "*.txt" 2>/dev/null | wc -l)
echo "✓ Total Stooq TXT files ready: $TOTAL_FILES"
echo ""

echo "🌐 Starting Web Interface..."
echo "========================================"

# Start the web server
python3 web_gui.py
