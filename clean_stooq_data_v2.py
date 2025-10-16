#!/usr/bin/env python3
"""
Clean Stooq Data V2 - Focus on actual Stooq files and handle date issues
"""

import pandas as pd
import os
import glob
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_stooq_file(file_path, output_dir=None):
    """
    Clean a single Stooq file by removing invalid dates and malformed entries
    """
    try:
        print(f"Processing: {os.path.basename(file_path)}")
        
        # Read the file with low_memory=False to avoid mixed type warnings
        df = pd.read_csv(file_path, delimiter=',', low_memory=False)
        
        print(f"Original rows: {len(df)}")
        
        # Check if it's a valid Stooq file
        required_cols = ['<TICKER>', '<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Skipping {file_path} - missing required columns: {missing_cols}")
            return None
            
        # Convert DATE column to string and clean
        df['<DATE>'] = df['<DATE>'].astype(str)
        df['<TIME>'] = df['<TIME>'].astype(str)
        
        # Remove rows with NaN or empty dates
        df = df[df['<DATE>'].notna()]
        df = df[df['<DATE>'] != 'nan']
        df = df[df['<DATE>'] != '']
        
        print(f"After removing NaN dates: {len(df)}")
        
        # Extract year from date string (format: YYYYMMDD)
        df['year'] = df['<DATE>'].str[:4]
        
        # Filter out future dates and invalid years
        current_year = datetime.now().year
        valid_years = []
        for year_str in df['year'].unique():
            try:
                year_int = int(year_str)
                if 1900 <= year_int <= current_year:
                    valid_years.append(year_str)
            except:
                pass
        
        df = df[df['year'].isin(valid_years)]
        
        print(f"After year filtering: {len(df)}")
        
        # Try to parse dates and remove invalid ones
        try:
            df['parsed_date'] = pd.to_datetime(df['<DATE>'], format='%Y%m%d', errors='coerce')
            valid_dates = df['parsed_date'].notna()
            df = df[valid_dates].copy()
            
            print(f"After date parsing: {len(df)}")
            
        except Exception as e:
            print(f"Date parsing failed: {e}")
            return None
            
        # Clean up temporary columns
        df = df.drop(['year', 'parsed_date'], axis=1)
        
        # Validate numeric columns
        numeric_cols = ['<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>', '<OPENINT>']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove rows with NaN in critical columns
        critical_cols = ['<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>']
        df = df.dropna(subset=critical_cols)
        
        print(f"After numeric validation: {len(df)}")
        
        # Skip files with no valid data
        if len(df) == 0:
            print(f"No valid data remaining in {file_path}")
            return None
        
        # Save cleaned file
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.basename(file_path)
            output_path = os.path.join(output_dir, f"cleaned_{filename}")
        else:
            output_path = file_path.replace('.txt', '_cleaned.txt')
            
        df.to_csv(output_path, index=False)
        print(f"Saved cleaned file: {os.path.basename(output_path)}")
        
        return output_path
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def main():
    """Clean all Stooq files in the import directory"""
    
    stooq_dir = "/app/data/stooq_import"
    output_dir = "/app/data/stooq_cleaned"
    
    # Find only the actual Stooq data files (not the mixed files)
    stooq_patterns = [
        os.path.join(stooq_dir, "data", "**", "*.txt"),  # Main data directory
        os.path.join(stooq_dir, "data_dh5.txt")  # The problematic file
    ]
    
    txt_files = []
    for pattern in stooq_patterns:
        txt_files.extend(glob.glob(pattern, recursive=True))
    
    # Filter to only include files with Stooq headers
    valid_stooq_files = []
    for file_path in txt_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if '<TICKER>' in first_line:
                    valid_stooq_files.append(file_path)
        except:
            pass
    
    print(f"Found {len(valid_stooq_files)} valid Stooq files to process")
    
    # Process only first 50 files for testing
    files_to_process = valid_stooq_files[:50]
    print(f"Processing first {len(files_to_process)} files for testing...")
    
    cleaned_files = []
    for file_path in files_to_process:
        cleaned_file = clean_stooq_file(file_path, output_dir)
        if cleaned_file:
            cleaned_files.append(cleaned_file)
    
    print(f"\nCleaning complete!")
    print(f"Processed {len(files_to_process)} files")
    print(f"Successfully cleaned {len(cleaned_files)} files")
    print(f"Cleaned files saved to: {output_dir}")
    
    # Show some statistics
    if cleaned_files:
        print(f"\nCleaned files:")
        for f in cleaned_files[:10]:  # Show first 10
            print(f"  - {os.path.basename(f)}")
        if len(cleaned_files) > 10:
            print(f"  ... and {len(cleaned_files) - 10} more")

if __name__ == "__main__":
    main()
