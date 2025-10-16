#!/bin/bash

# REDLINE Simple ARM64 Runner with Stooq Data Import
# This script processes Stooq data without interactive CLI

echo "========================================"
echo "REDLINE ARM64 Simple Processing"
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
    
    # Show some sample files
    echo ""
    echo "Sample Stooq files found:"
    find "$STOOQ_DIR" -name "*.txt" -type f | head -5 | while read file; do
        echo "  - $(basename "$file")"
    done
    
    if [ "$TOTAL_FILES" -gt 5 ]; then
        echo "  ... and $(($TOTAL_FILES - 5)) more files"
    fi
else
    echo "ℹ No Stooq files found in Downloads"
fi

echo "========================================"
echo "Starting REDLINE ARM64 container for data processing..."
echo ""

# Run Docker container to process the data
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/data:/app/data \
  redline_arm \
  python3 -c "
import sys
import os
sys.path.append('/app')

print('=' * 60)
print('REDLINE Data Processing')
print('=' * 60)
print('')

try:
    from data_module import DataLoader
    print('✓ DataLoader imported successfully')
    
    # Check available data files
    stooq_dir = '/app/data/stooq_import'
    if os.path.exists(stooq_dir):
        txt_files = [f for f in os.listdir(stooq_dir) if f.endswith('.txt')]
        print(f'✓ Found {len(txt_files)} TXT files')
        
        if txt_files:
            print('')
            print('Processing first 5 Stooq files as demonstration...')
            
            loader = DataLoader()
            processed_count = 0
            
            # Process first 5 files
            for i, file in enumerate(txt_files[:5]):
                try:
                    file_path = os.path.join(stooq_dir, file)
                    print(f'Processing {i+1}/5: {file}')
                    
                    # Try to load the file
                    df = loader.load_file_by_type(file_path, 'txt')
                    if df is not None and not df.empty:
                        print(f'  ✓ Loaded {len(df)} rows')
                        print(f'  ✓ Columns: {list(df.columns)}')
                        print(f'  ✓ Date range: {df[\"timestamp\"].min()} to {df[\"timestamp\"].max()}')
                        processed_count += 1
                    else:
                        print(f'  ⚠ No data loaded (might not be Stooq format)')
                        
                except Exception as e:
                    print(f'  ✗ Error: {str(e)[:100]}...')
            
            print('')
            print(f'Successfully processed {processed_count} out of 5 files')
            print('')
            print('Data processing complete!')
            print('You can now use the processed data with REDLINE.')
            
        else:
            print('No TXT files found in stooq_import directory')
    else:
        print('Stooq import directory not found')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

print('')
print('REDLINE processing session ended.')
"

echo "========================================"
echo "Done!"
