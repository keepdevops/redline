

#!/bin/bash

# Copy Stooq files from Downloads to data directory
echo "========================================"
echo "Checking for Stooq files in Downloads..."
echo "========================================"

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
    echo "✓ Total Stooq TXT files ready:    $TOTAL_FILES"
else
    echo "ℹ No Stooq files found in Downloads"
fi

echo "========================================"

echo "RUN====ARM-OSX=============="
echo "RUN====ARM-OSX=============="
echo "RUN====ARM-OSX=============="
echo "RUN====ARM-OSX=============="
echo "RUN====ARM-OSX=============="

# Run REDLINE in command-line mode (no GUI) for ARM64
echo "Starting REDLINE ARM container in command-line mode..."
echo "Note: GUI mode has X11 forwarding issues on macOS ARM. Using CLI mode."

# Run Docker container without GUI dependencies
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/data:/app/data \
  redline_arm python3 /app/data_module.py --task=load

echo "DONE=================="
echo "DONE=================="
echo "DONE=================="
echo "DONE=================="
echo "DONE=================="

