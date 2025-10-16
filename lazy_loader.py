#!/usr/bin/env python3
"""
Lazy file loader for processing large datasets in batches to avoid memory issues.
"""

import os
import logging
import pandas as pd
import duckdb
from data_loader import DataLoader


class LazyFileLoader:
    """Lazy file loader that processes files in batches to avoid memory issues"""
    
    def __init__(self, file_paths, batch_size=100):
        """
        Initialize lazy file loader.
        
        Args:
            file_paths: List of file paths to process
            batch_size: Number of files to process in each batch
        """
        self.file_paths = file_paths
        self.batch_size = batch_size
        self.current_batch = 0
        self.total_files = len(file_paths)
        
    def get_batch_count(self):
        """Get total number of batches needed"""
        return (self.total_files + self.batch_size - 1) // self.batch_size
        
    def get_batch_files(self, batch_idx):
        """Get file paths for a specific batch"""
        start_idx = batch_idx * self.batch_size
        end_idx = min(start_idx + self.batch_size, self.total_files)
        return self.file_paths[start_idx:end_idx]
        
    def process_batch(self, batch_idx, output_db_path, input_format='txt', progress_callback=None):
        """
        Process one batch of files and append to DuckDB.
        
        Args:
            batch_idx: Index of the batch to process
            output_db_path: Path to output DuckDB file
            input_format: Input file format ('txt' for Stooq)
            progress_callback: Function to call for progress updates
            
        Returns:
            Number of successfully processed files in this batch
        """
        batch_files = self.get_batch_files(batch_idx)
        batch_df_list = []
        
        for idx, file_path in enumerate(batch_files):
            try:
                # Read the raw data
                df = pd.read_csv(file_path)
                
                # If input format is txt (Stooq), standardize the columns
                if input_format.lower() == 'txt':
                    # Create a temporary DataLoader instance to use the standardize method
                    temp_loader = DataLoader()
                    df = temp_loader._standardize_txt_columns(df)
                
                if df is not None and not df.empty:
                    batch_df_list.append(df)
                    
                # Update progress for this batch
                if progress_callback:
                    file_progress = (idx + 1) / len(batch_files)
                    progress_callback(batch_idx, file_progress)
                    
            except Exception as error:
                logging.error(f"Error processing file {file_path}: {str(error)}")
                print(f"Failed to process {os.path.basename(file_path)}: {str(error)}")
                continue
        
        # Combine batch dataframes and save to DuckDB
        if batch_df_list:
            batch_data = pd.concat(batch_df_list, ignore_index=True)
            
            # Initialize or append to DuckDB
            if batch_idx == 0:
                # First batch - create new table
                conn = duckdb.connect(output_db_path)
                conn.execute("DROP TABLE IF EXISTS tickers_data")
                conn.execute("CREATE TABLE tickers_data AS SELECT * FROM batch_data")
                conn.close()
            else:
                # Subsequent batches - append to existing table
                conn = duckdb.connect(output_db_path)
                conn.execute("INSERT INTO tickers_data SELECT * FROM batch_data")
                conn.close()
            
            # Clear memory
            del batch_data
            del batch_df_list
            
        return len(batch_df_list) if batch_df_list else 0
        
    def process_all_batches(self, output_db_path, input_format='txt', progress_callback=None):
        """
        Process all batches sequentially.
        
        Args:
            output_db_path: Path to output DuckDB file
            input_format: Input file format ('txt' for Stooq)
            progress_callback: Function to call for progress updates
            
        Returns:
            Total number of successfully processed files
        """
        total_batches = self.get_batch_count()
        total_processed = 0
        
        print(f"Processing {self.total_files} files in {total_batches} batches...")
        
        for batch_idx in range(total_batches):
            print(f"Processing batch {batch_idx + 1}/{total_batches}...")
            
            processed_count = self.process_batch(
                batch_idx, 
                output_db_path, 
                input_format, 
                progress_callback
            )
            
            total_processed += processed_count
            
            if progress_callback:
                progress_callback(batch_idx, 1.0)  # Batch complete
                
        print(f"Completed processing {total_processed} files successfully")
        return total_processed

    def get_file_info(self):
        """Get information about the files to be processed"""
        return {
            'total_files': self.total_files,
            'batch_size': self.batch_size,
            'total_batches': self.get_batch_count(),
            'estimated_memory_per_batch': f"~{self.batch_size} files worth"
        }
