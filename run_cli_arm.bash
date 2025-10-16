#!/bin/bash

# REDLINE CLI Docker Runner for ARM64 macOS with Stooq Data Import
# This script provides a command-line interface for data processing

echo "========================================"
echo "REDLINE ARM64 CLI with Stooq Import"
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
echo "Starting REDLINE ARM64 container in CLI mode..."
echo ""

# Run Docker container with interactive CLI
docker run --rm -it \
  -v $(pwd):/app \
  -v $(pwd)/data:/app/data \
  --name redline_cli_arm \
  redline_arm \
  python3 -c "
import sys
sys.path.append('/app')

print('=' * 60)
print('REDLINE CLI Interface')
print('=' * 60)
print('')

# Import the data module
try:
    from data_module import DataLoader
    print('✓ DataLoader imported successfully')
    
    # Check available data files
    import os
    stooq_dir = '/app/data/stooq_import'
    if os.path.exists(stooq_dir):
        txt_files = [f for f in os.listdir(stooq_dir) if f.endswith('.txt')]
        print(f'✓ Found {len(txt_files)} Stooq TXT files')
        
        if txt_files:
            print('')
            print('Sample files available:')
            for i, file in enumerate(txt_files[:10]):
                print(f'  {i+1:2d}. {file}')
            if len(txt_files) > 10:
                print(f'  ... and {len(txt_files) - 10} more files')
            
            print('')
            print('Available commands:')
            print('  1. Process all Stooq files')
            print('  2. Process specific file')
            print('  3. List all files')
            print('  4. Exit')
            print('')
            
            while True:
                try:
                    choice = input('Enter your choice (1-4): ').strip()
                    
                    if choice == '1':
                        print('Processing all Stooq files...')
                        loader = DataLoader()
                        processed_count = 0
                        for file in txt_files:
                            try:
                                file_path = os.path.join(stooq_dir, file)
                                print(f'Processing: {file}')
                                df = loader.load_file_by_type(file_path, 'txt')
                                if df is not None and not df.empty:
                                    print(f'  ✓ Loaded {len(df)} rows')
                                    processed_count += 1
                                else:
                                    print(f'  ⚠ No data loaded')
                            except Exception as e:
                                print(f'  ✗ Error: {e}')
                        print(f'Processed {processed_count} files successfully')
                        break
                    
                    elif choice == '2':
                        print('Available files:')
                        for i, file in enumerate(txt_files[:20]):  # Show first 20
                            print(f'  {i+1:2d}. {file}')
                        if len(txt_files) > 20:
                            print(f'  ... and {len(txt_files) - 20} more files')
                        
                        try:
                            file_num = int(input('Enter file number: ')) - 1
                            if 0 <= file_num < len(txt_files):
                                selected_file = txt_files[file_num]
                                file_path = os.path.join(stooq_dir, selected_file)
                                print(f'Processing: {selected_file}')
                                
                                loader = DataLoader()
                                df = loader.load_file_by_type(file_path, 'txt')
                                if df is not None and not df.empty:
                                    print(f'✓ Loaded {len(df)} rows')
                                    print('')
                                    print('Data preview:')
                                    print(df.head())
                                    print('')
                                    print('Data info:')
                                    print(df.info())
                                else:
                                    print('⚠ No data loaded')
                            else:
                                print('Invalid file number')
                        except ValueError:
                            print('Please enter a valid number')
                        break
                    
                    elif choice == '3':
                        print('All Stooq files:')
                        for i, file in enumerate(txt_files):
                            print(f'  {i+1:3d}. {file}')
                        print('')
                    
                    elif choice == '4':
                        print('Exiting...')
                        break
                    
                    else:
                        print('Invalid choice. Please enter 1-4.')
                
                except KeyboardInterrupt:
                    print('\\nExiting...')
                    break
                except EOFError:
                    print('\\nExiting...')
                    break
        else:
            print('No TXT files found in stooq_import directory')
    else:
        print('Stooq import directory not found')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

print('')
print('REDLINE CLI session ended.')
"

echo "========================================"
echo "Done!"
