#!/usr/bin/env python3
"""
Progress tracking utilities for long-running operations.
"""

import time
import threading
import logging
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ProgressInfo:
    """Progress information container"""
    current_item: int
    total_items: int
    current_batch: int
    total_batches: int
    start_time: float
    current_time: float
    items_per_second: float
    estimated_remaining: float
    
    @property
    def percentage(self) -> float:
        """Get completion percentage"""
        if self.total_items == 0:
            return 0.0
        return (self.current_item / self.total_items) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        return self.current_time - self.start_time
    
    @property
    def eta_seconds(self) -> float:
        """Get estimated time remaining in seconds"""
        return self.estimated_remaining
    
    @property
    def eta_formatted(self) -> str:
        """Get formatted ETA string"""
        if self.eta_seconds < 60:
            return f"{self.eta_seconds:.0f}s"
        elif self.eta_seconds < 3600:
            return f"{self.eta_seconds/60:.1f}m"
        else:
            return f"{self.eta_seconds/3600:.1f}h"


class ProgressTracker:
    """Progress tracker for batch operations"""
    
    def __init__(self, total_items: int, batch_size: int = 100, 
                 callback: Optional[Callable] = None):
        """
        Initialize progress tracker.
        
        Args:
            total_items: Total number of items to process
            batch_size: Size of each batch
            callback: Optional callback function for progress updates
        """
        self.total_items = total_items
        self.batch_size = batch_size
        self.total_batches = (total_items + batch_size - 1) // batch_size
        self.callback = callback
        
        self.current_item = 0
        self.current_batch = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.items_per_second = 0.0
        
        self.lock = threading.Lock()
    
    def update(self, items_processed: int, batch_idx: int = None):
        """
        Update progress.
        
        Args:
            items_processed: Number of items processed in this update
            batch_idx: Current batch index (optional)
        """
        with self.lock:
            current_time = time.time()
            
            # Update counters
            self.current_item += items_processed
            if batch_idx is not None:
                self.current_batch = batch_idx + 1
            
            # Calculate processing rate
            time_diff = current_time - self.last_update_time
            if time_diff > 0:
                self.items_per_second = items_processed / time_diff
            
            # Calculate ETA
            remaining_items = self.total_items - self.current_item
            if self.items_per_second > 0:
                self.estimated_remaining = remaining_items / self.items_per_second
            else:
                self.estimated_remaining = 0.0
            
            # Create progress info
            progress_info = ProgressInfo(
                current_item=self.current_item,
                total_items=self.total_items,
                current_batch=self.current_batch,
                total_batches=self.total_batches,
                start_time=self.start_time,
                current_time=current_time,
                items_per_second=self.items_per_second,
                estimated_remaining=self.estimated_remaining
            )
            
            # Call callback if provided
            if self.callback:
                try:
                    self.callback(progress_info)
                except Exception as e:
                    logging.error(f"Error in progress callback: {str(e)}")
            
            self.last_update_time = current_time
    
    def get_progress_info(self) -> ProgressInfo:
        """Get current progress information"""
        with self.lock:
            current_time = time.time()
            return ProgressInfo(
                current_item=self.current_item,
                total_items=self.total_items,
                current_batch=self.current_batch,
                total_batches=self.total_batches,
                start_time=self.start_time,
                current_time=current_time,
                items_per_second=self.items_per_second,
                estimated_remaining=self.estimated_remaining
            )
    
    def is_complete(self) -> bool:
        """Check if processing is complete"""
        return self.current_item >= self.total_items
    
    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary"""
        info = self.get_progress_info()
        return {
            'total_items': self.total_items,
            'processed_items': self.current_item,
            'remaining_items': self.total_items - self.current_item,
            'percentage': info.percentage,
            'elapsed_time': info.elapsed_time,
            'eta': info.eta_formatted,
            'items_per_second': self.items_per_second,
            'total_batches': self.total_batches,
            'completed_batches': self.current_batch
        }


class BatchProgressTracker:
    """Progress tracker specifically for batch operations"""
    
    def __init__(self, file_paths: List[str], batch_size: int = 100):
        """
        Initialize batch progress tracker.
        
        Args:
            file_paths: List of file paths to process
            batch_size: Size of each batch
        """
        self.file_paths = file_paths
        self.batch_size = batch_size
        self.total_files = len(file_paths)
        self.total_batches = (self.total_files + batch_size - 1) // batch_size
        
        self.tracker = ProgressTracker(
            total_items=self.total_files,
            batch_size=batch_size,
            callback=self._progress_callback
        )
        
        self.batch_info = {}
    
    def _progress_callback(self, progress_info: ProgressInfo):
        """Internal progress callback"""
        self._log_progress(progress_info)
    
    def _log_progress(self, info: ProgressInfo):
        """Log progress information"""
        if info.current_item % 100 == 0 or info.current_item == self.total_files:
            logging.info(
                f"Progress: {info.current_item}/{info.total_files} "
                f"({info.percentage:.1f}%) - "
                f"Batch {info.current_batch}/{info.total_batches} - "
                f"Rate: {info.items_per_second:.1f} files/s - "
                f"ETA: {info.eta_formatted}"
            )
    
    def start_batch(self, batch_idx: int, batch_files: List[str]):
        """
        Start processing a batch.
        
        Args:
            batch_idx: Batch index
            batch_files: Files in this batch
        """
        self.batch_info[batch_idx] = {
            'files': batch_files,
            'start_time': time.time(),
            'processed': 0
        }
        logging.info(f"Starting batch {batch_idx + 1}/{self.total_batches} with {len(batch_files)} files")
    
    def update_batch_progress(self, batch_idx: int, files_processed: int):
        """
        Update progress for current batch.
        
        Args:
            batch_idx: Batch index
            files_processed: Number of files processed in this batch
        """
        if batch_idx in self.batch_info:
            self.batch_info[batch_idx]['processed'] = files_processed
        
        self.tracker.update(files_processed, batch_idx)
    
    def complete_batch(self, batch_idx: int, success_count: int, error_count: int = 0):
        """
        Mark batch as complete.
        
        Args:
            batch_idx: Batch index
            success_count: Number of successfully processed files
            error_count: Number of files with errors
        """
        if batch_idx in self.batch_info:
            batch_info = self.batch_info[batch_idx]
            batch_info['completed'] = True
            batch_info['success_count'] = success_count
            batch_info['error_count'] = error_count
            batch_info['end_time'] = time.time()
            batch_info['duration'] = batch_info['end_time'] - batch_info['start_time']
            
            logging.info(
                f"Completed batch {batch_idx + 1}/{self.total_batches}: "
                f"{success_count} successful, {error_count} errors, "
                f"duration: {batch_info['duration']:.1f}s"
            )
    
    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary"""
        summary = self.tracker.get_summary()
        
        # Add batch-specific information
        completed_batches = sum(1 for info in self.batch_info.values() if info.get('completed', False))
        total_success = sum(info.get('success_count', 0) for info in self.batch_info.values())
        total_errors = sum(info.get('error_count', 0) for info in self.batch_info.values())
        
        summary.update({
            'completed_batches': completed_batches,
            'total_successful_files': total_success,
            'total_errors': total_errors,
            'batch_info': self.batch_info
        })
        
        return summary
