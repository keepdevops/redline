#!/usr/bin/env python3
"""
Clean Stooq Data - Remove invalid dates and malformed entries
"""

import pandas as pd
import os
import glob
from datetime import datetime, date
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_stooq_file(file_path, output_dir=None):
    """
    Clean a single Stooq file by removing invalid dates and malformed entries
    """
    try:
        print(f"Processing: {file_path}")
        
        # Read the file
        df = pd.read_csv(file_path, delimiter=',')
        
        print(f"Original rows: {len(df)}")
        
        # Check if it's a valid Stooq file
        required_cols = ['<TICKER>', '<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"Skipping {file_path} - missing required columns: {missing_cols}")
            return None
            
        # Convert DATE column to datetime and filter valid dates
        current_year = datetime.now().year
        max_year = current_year + 1  # Allow up to next year
        
        # Convert DATE to string and validate
        df['<DATE>'] = df['<DATE>'].astype(str)
        
        # Extract year from date string (format: YYYYMMDD)
        df['year'] = df['<DATE>'].str[:4].astype(int)
        
        # Filter out future dates and invalid years
        valid_years = (df['year'] >= 1900) & (df['year'] <= max_year)
        df = df[valid_years].copy()
        
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
        
        # Save cleaned file
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.basename(file_path)
            output_path = os.path.join(output_dir, f"cleaned_{filename}")
        else:
            output_path = file_path.replace('.txt', '_cleaned.txt')
            
        df.to_csv(output_path, index=False)
        print(f"Saved cleaned file: {output_path}")
        
        return output_path
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def main():
    """Clean all Stooq files in the import directory"""
    
    stooq_dir = "/app/data/stooq_import"
    output_dir = "/app/data/stooq_cleaned"
    
    # Find all TXT files
    txt_files = glob.glob(os.path.join(stooq_dir, "*.txt"))
    
    print(f"Found {len(txt_files)} TXT files to process")
    
    cleaned_files = []
    for file_path in txt_files:
        cleaned_file = clean_stooq_file(file_path, output_dir)
        if cleaned_file:
            cleaned_files.append(cleaned_file)
    
    print(f"\nCleaning complete!")
    print(f"Processed {len(txt_files)} files")
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
