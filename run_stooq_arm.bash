#!/bin/bash

# REDLINE Stooq Data Processor for ARM64 macOS
# This script processes only actual Stooq data files

echo "========================================"
echo "REDLINE ARM64 Stooq Data Processor"
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

echo "========================================"
echo "Starting REDLINE ARM64 container for Stooq processing..."
echo ""

# Run Docker container to process the Stooq data
docker run --rm \
  -v $(pwd):/app \
  -v $(pwd)/data:/app/data \
  redline_arm \
  python3 -c "
import sys
import os
sys.path.append('/app')

print('=' * 60)
print('REDLINE Stooq Data Processing')
print('=' * 60)
print('')

try:
    from data_module import DataLoader
    print('✓ DataLoader imported successfully')
    
    # Check available data files and identify Stooq files
    stooq_dir = '/app/data/stooq_import'
    if os.path.exists(stooq_dir):
        all_files = [f for f in os.listdir(stooq_dir) if f.endswith('.txt')]
        print(f'✓ Found {len(all_files)} total TXT files')
        
        # Identify actual Stooq files by checking headers
        stooq_files = []
        for file in all_files:
            file_path = os.path.join(stooq_dir, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if '<TICKER>' in first_line and '<DATE>' in first_line:
                        stooq_files.append(file)
            except:
                continue
        
        print(f'✓ Identified {len(stooq_files)} actual Stooq data files')
        
        if stooq_files:
            print('')
            print('Stooq files found:')
            for i, file in enumerate(stooq_files[:10]):  # Show first 10
                print(f'  {i+1:2d}. {file}')
            if len(stooq_files) > 10:
                print(f'  ... and {len(stooq_files) - 10} more files')
            
            print('')
            print('Processing Stooq files...')
            
            loader = DataLoader()
            processed_count = 0
            total_rows = 0
            
            # Process all Stooq files
            for i, file in enumerate(stooq_files):
                try:
                    file_path = os.path.join(stooq_dir, file)
                    print(f'Processing {i+1}/{len(stooq_files)}: {file}')
                    
                    # Load the Stooq file
                    df = loader.load_file_by_type(file_path, 'txt')
                    if df is not None and not df.empty:
                        rows = len(df)
                        total_rows += rows
                        print(f'  ✓ Loaded {rows} rows')
                        print(f'  ✓ Columns: {list(df.columns)}')
                        print(f'  ✓ Date range: {df[\"timestamp\"].min()} to {df[\"timestamp\"].max()}')
                        print(f'  ✓ Tickers: {df[\"ticker\"].nunique()} unique tickers')
                        processed_count += 1
                    else:
                        print(f'  ⚠ No data loaded')
                        
                except Exception as e:
                    print(f'  ✗ Error: {str(e)[:100]}...')
            
            print('')
            print('=' * 60)
            print('PROCESSING SUMMARY')
            print('=' * 60)
            print(f'✓ Successfully processed: {processed_count} out of {len(stooq_files)} files')
            print(f'✓ Total data rows: {total_rows:,}')
            print('')
            print('Stooq data processing complete!')
            print('The data is now ready for analysis with REDLINE.')
            
        else:
            print('No actual Stooq data files found')
            print('Looking for files with <TICKER> and <DATE> headers...')
    else:
        print('Stooq import directory not found')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

print('')
print('REDLINE Stooq processing session ended.')
"

echo "========================================"
echo "Done!"
