#!/usr/bin/env python3
"""
REDLINE CLI version - processes Stooq data without GUI
"""

import sys
import os
from data_module import DataLoader
from data_module_shared import DatabaseConnector

def main():
    print("🚀 REDLINE CLI - Processing Stooq Data")
    print("=" * 50)
    
    # Initialize components
    try:
        loader = DataLoader()
        connector = DatabaseConnector()
        print("✅ Components initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize components: {e}")
        return 1
    
    # Find Stooq files
    stooq_dir = "data/stooq_import"
    if not os.path.exists(stooq_dir):
        print(f"❌ Stooq import directory not found: {stooq_dir}")
        return 1
    
    # Get list of TXT files
    import glob
    txt_files = glob.glob(os.path.join(stooq_dir, "*.txt"))
    
    if not txt_files:
        print(f"❌ No TXT files found in {stooq_dir}")
        return 1
    
    print(f"📁 Found {len(txt_files)} TXT files to process")
    
    # Process each file
    processed_count = 0
    error_count = 0
    
    for i, file_path in enumerate(txt_files[:5]):  # Process first 5 files as test
        try:
            print(f"🔄 Processing {i+1}/5: {os.path.basename(file_path)}")
            
            # Load and standardize the file
            df = loader.load_file_by_type(file_path, 'txt')
            
            if df is not None and not df.empty:
                print(f"   ✅ Successfully processed {len(df)} rows")
                processed_count += 1
            else:
                print(f"   ⚠️  No data found in file")
                
        except Exception as e:
            print(f"   ❌ Error processing file: {e}")
            error_count += 1
    
    print("=" * 50)
    print(f"📊 Processing Summary:")
    print(f"   ✅ Successfully processed: {processed_count} files")
    print(f"   ❌ Errors: {error_count} files")
    print(f"   📁 Total files found: {len(txt_files)}")
    
    return 0 if error_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
