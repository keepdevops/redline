#!/usr/bin/env python3
"""
File operations and utilities for REDLINE data processing.
"""

import os
import glob
import logging
from typing import List, Dict, Optional
from pathlib import Path


class FileOperations:
    """Utility class for file operations"""
    
    @staticmethod
    def find_stooq_files(directory: str) -> List[str]:
        """
        Find all Stooq format files in a directory.
        
        Args:
            directory: Directory to search
            
        Returns:
            List of file paths
        """
        try:
            # Look for TXT files that might be Stooq format
            txt_files = glob.glob(os.path.join(directory, "**/*.txt"), recursive=True)
            
            # Filter for actual Stooq files by checking headers
            stooq_files = []
            for file_path in txt_files:
                if FileOperations.is_stooq_file(file_path):
                    stooq_files.append(file_path)
            
            return stooq_files
            
        except Exception as e:
            logging.error(f"Error finding Stooq files in {directory}: {str(e)}")
            return []
    
    @staticmethod
    def is_stooq_file(file_path: str) -> bool:
        """
        Check if a file is in Stooq format.
        
        Args:
            file_path: Path to file to check
            
        Returns:
            True if file appears to be Stooq format
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
                
            # Check for Stooq format header
            required_cols = ['<TICKER>', '<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>']
            header_cols = [col.strip() for col in header.split(',')]
            
            # Check if all required columns are present
            return all(col in header_cols for col in required_cols)
            
        except Exception as e:
            logging.debug(f"Error checking Stooq format for {file_path}: {str(e)}")
            return False
    
    @staticmethod
    def categorize_files(file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Categorize files by type based on directory structure.
        
        Args:
            file_paths: List of file paths to categorize
            
        Returns:
            Dictionary with categories as keys and file lists as values
        """
        categories = {
            'us_stocks': [],
            'world_bonds': [],
            'cryptocurrencies': [],
            'money_market': [],
            'indices': [],
            'other': []
        }
        
        for file_path in file_paths:
            path_parts = Path(file_path).parts
            
            if 'us' in path_parts:
                if 'stocks' in path_parts or 'etfs' in path_parts:
                    categories['us_stocks'].append(file_path)
                else:
                    categories['other'].append(file_path)
            elif 'world' in path_parts:
                if 'bonds' in path_parts:
                    categories['world_bonds'].append(file_path)
                elif 'cryptocurrencies' in path_parts:
                    categories['cryptocurrencies'].append(file_path)
                elif 'money market' in path_parts:
                    categories['money_market'].append(file_path)
                elif 'indices' in path_parts:
                    categories['indices'].append(file_path)
                else:
                    categories['other'].append(file_path)
            else:
                categories['other'].append(file_path)
        
        return categories
    
    @staticmethod
    def get_file_info(file_path: str) -> Dict[str, any]:
        """
        Get information about a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information
        """
        try:
            stat = os.stat(file_path)
            return {
                'path': file_path,
                'name': os.path.basename(file_path),
                'size': stat.st_size,
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': stat.st_mtime,
                'extension': os.path.splitext(file_path)[1].lower(),
                'directory': os.path.dirname(file_path)
            }
        except Exception as e:
            logging.error(f"Error getting file info for {file_path}: {str(e)}")
            return {}
    
    @staticmethod
    def get_directory_structure(directory: str) -> Dict[str, any]:
        """
        Get directory structure information.
        
        Args:
            directory: Directory to analyze
            
        Returns:
            Dictionary with directory structure info
        """
        try:
            structure = {
                'total_files': 0,
                'total_size_mb': 0,
                'categories': {},
                'file_types': {}
            }
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_info = FileOperations.get_file_info(file_path)
                    
                    structure['total_files'] += 1
                    structure['total_size_mb'] += file_info.get('size_mb', 0)
                    
                    # Count file types
                    ext = file_info.get('extension', '')
                    structure['file_types'][ext] = structure['file_types'].get(ext, 0) + 1
                    
                    # Categorize by directory
                    rel_path = os.path.relpath(root, directory)
                    structure['categories'][rel_path] = structure['categories'].get(rel_path, 0) + 1
            
            return structure
            
        except Exception as e:
            logging.error(f"Error analyzing directory structure for {directory}: {str(e)}")
            return {}
    
    @staticmethod
    def create_batch_groups(file_paths: List[str], batch_size: int = 100) -> List[List[str]]:
        """
        Create batches of file paths.
        
        Args:
            file_paths: List of file paths
            batch_size: Size of each batch
            
        Returns:
            List of batches
        """
        batches = []
        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i:i + batch_size]
            batches.append(batch)
        return batches
    
    @staticmethod
    def estimate_processing_time(file_paths: List[str], files_per_second: float = 10.0) -> Dict[str, any]:
        """
        Estimate processing time for files.
        
        Args:
            file_paths: List of file paths to process
            files_per_second: Estimated processing rate
            
        Returns:
            Dictionary with time estimates
        """
        total_files = len(file_paths)
        total_size_mb = sum(FileOperations.get_file_info(f).get('size_mb', 0) for f in file_paths)
        
        estimated_seconds = total_files / files_per_second
        estimated_minutes = estimated_seconds / 60
        estimated_hours = estimated_minutes / 60
        
        return {
            'total_files': total_files,
            'total_size_mb': round(total_size_mb, 2),
            'estimated_seconds': round(estimated_seconds, 2),
            'estimated_minutes': round(estimated_minutes, 2),
            'estimated_hours': round(estimated_hours, 2),
            'files_per_second': files_per_second
        }
    
    @staticmethod
    def cleanup_temp_files(directory: str = ".", pattern: str = "temp_*"):
        """
        Clean up temporary files.
        
        Args:
            directory: Directory to clean
            pattern: Pattern for temp files
        """
        try:
            temp_files = glob.glob(os.path.join(directory, pattern))
            for temp_file in temp_files:
                os.remove(temp_file)
                logging.info(f"Cleaned up temporary file: {temp_file}")
        except Exception as e:
            logging.error(f"Error cleaning up temp files: {str(e)}")
    
    @staticmethod
    def ensure_directory_exists(directory: str):
        """
        Ensure directory exists, create if it doesn't.
        
        Args:
            directory: Directory path
        """
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.error(f"Error creating directory {directory}: {str(e)}")
            raise
