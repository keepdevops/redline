#!/usr/bin/env python3
"""
User manual and help system for REDLINE application.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext


class UserManual:
    """User manual and help system"""
    
    def __init__(self):
        """Initialize user manual"""
        self.manual_content = self._get_manual_content()
    
    def _get_manual_content(self) -> str:
        """Get the complete manual content"""
        return """
REDLINE DATA CONVERSION UTILITY - USER MANUAL

============================
TABLE OF CONTENTS
============================
1. Introduction
2. Getting Started
3. Data Loader Tab
4. Data View Tab
5. Lazy Loading Features
6. File Formats & Standards
7. Advanced Features
8. Troubleshooting
9. Best Practices

============================
1. INTRODUCTION
============================
REDLINE is a powerful tool for converting, cleaning, and managing financial market data. 
It provides a user-friendly graphical interface for:
• Loading and viewing market data files
• Converting between different file formats
• Preprocessing and cleaning data
• Analyzing data quality and statistics
• Managing large datasets efficiently with lazy loading

============================
2. GETTING STARTED
============================
Key Concepts:
• Workspace: The main window with Data Loader and Data View tabs
• File Formats: Supported types (CSV, JSON, DuckDB, Parquet, Feather)
• Lazy Loading: Efficient processing of large datasets in batches
• Data Processing: Converting, cleaning, and analyzing data
• Data View: Browsing and managing your data files with virtual scrolling

Basic Workflow:
1. Load data files using the Data Loader tab
2. Preview and verify data content
3. Process or convert data as needed (automatically uses lazy loading for large datasets)
4. View and analyze results in Data View tab

============================
3. DATA LOADER TAB
============================
File Selection:
• Browse Files: Select input files from your system
• Select All: Select all files in the list
• Deselect All: Clear all selections
• Process Selected: Start processing the selected files

Format Selection:
• Input Format: Choose the format of your input files
• Output Format: Choose the desired output format

Progress Tracking:
• Progress bar shows processing status
• Real-time updates for large datasets
• Batch processing information for lazy loading

============================
4. DATA VIEW TAB
============================
File Viewing:
• Browse File: Select a file to view
• Virtual Scrolling: Efficiently view large datasets
• Advanced Filtering: Filter data with complex queries

Data Display:
• Pagination: Navigate through large datasets
• Column Sorting: Sort by any column
• Search: Find specific data entries

============================
5. LAZY LOADING FEATURES
============================
Automatic Lazy Loading:
• Automatically activates for datasets with >50 files
• Processes files in batches of 100
• Prevents memory issues with large datasets
• Real-time progress tracking

Batch Processing:
• Files processed in manageable chunks
• Memory cleared between batches
• Robust error handling per batch
• Detailed logging and progress reporting

Performance Benefits:
• Can handle 10,000+ files without crashing
• Memory usage stays constant regardless of dataset size
• Faster processing through optimized I/O
• Better error isolation and recovery

============================
6. FILE FORMATS & STANDARDS
============================
Supported Input Formats:
• TXT: Stooq format with <TICKER>, <DATE>, <TIME>, etc.
• CSV: Standard comma-separated values
• JSON: JSON Lines format
• Parquet: Apache Parquet files
• Feather: Fast columnar storage

Supported Output Formats:
• DuckDB: Fast analytical database
• CSV: Standard comma-separated values
• JSON: JSON Lines format
• Parquet: Apache Parquet files
• Feather: Fast columnar storage

Data Schema:
All data follows a standardized schema:
• ticker: Stock symbol or identifier
• timestamp: Date and time
• open: Opening price
• high: Highest price
• low: Lowest price
• close: Closing price
• vol: Volume
• openint: Open interest
• format: Source format

============================
7. ADVANCED FEATURES
============================
Virtual Scrolling:
• Only loads visible data into memory
• Supports datasets with millions of rows
• Smooth scrolling performance
• Intelligent caching system

Advanced Query Builder:
• SQL-like query construction
• Multiple operators: equals, contains, greater_than, etc.
• Complex conditions with AND/OR logic
• Query saving and loading

Technical Indicators:
• Moving averages (SMA, EMA)
• MACD (Moving Average Convergence Divergence)
• RSI (Relative Strength Index)
• Bollinger Bands
• Custom indicator calculations

============================
8. TROUBLESHOOTING
============================
Common Issues:

Memory Issues:
• Solution: Lazy loading automatically handles large datasets
• For manual control: Reduce batch size in configuration

File Format Errors:
• Check file encoding (should be UTF-8)
• Verify Stooq format headers
• Ensure proper column structure

Processing Errors:
• Check file permissions
• Verify sufficient disk space
• Review error logs for specific issues

Performance Issues:
• Enable virtual scrolling for large datasets
• Use DuckDB format for better performance
• Consider batch processing for very large files

============================
9. BEST PRACTICES
============================
File Organization:
• Keep related files in organized directories
• Use descriptive filenames
• Maintain consistent naming conventions

Data Processing:
• Always validate data before processing
• Use appropriate batch sizes for your system
• Monitor memory usage during processing
• Keep backups of original data

Performance Optimization:
• Use DuckDB format for analysis
• Enable virtual scrolling for large datasets
• Process data in logical batches
• Monitor system resources

Data Quality:
• Check for missing values
• Validate date/time formats
• Ensure numeric data consistency
• Review data statistics regularly

============================
SUPPORT & CONTACT
============================
For technical support or feature requests, please refer to the 
project documentation or contact the development team.

Version: 2.0 (with Lazy Loading)
Last Updated: 2024
        """
    
    def show_manual(self, parent=None):
        """Show the user manual in a popup window"""
        manual_window = tk.Toplevel(parent) if parent else tk.Tk()
        manual_window.title("REDLINE User Manual")
        manual_window.geometry("800x600")
        
        # Create scrolled text widget
        text_widget = scrolledtext.ScrolledText(
            manual_window,
            wrap=tk.WORD,
            width=100,
            height=35,
            font=('Courier', 10)
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Insert manual content
        text_widget.insert(tk.END, self.manual_content)
        text_widget.config(state=tk.DISABLED)
        
        # Add close button
        close_button = ttk.Button(manual_window, text="Close", command=manual_window.destroy)
        close_button.pack(pady=10)
        
        return manual_window


def show_user_manual_popup(parent):
    """Show user manual popup (backward compatibility)"""
    manual = UserManual()
    return manual.show_manual(parent)


def show_quick_help(parent):
    """Show quick help dialog"""
    help_window = tk.Toplevel(parent)
    help_window.title("Quick Help")
    help_window.geometry("600x400")
    
    help_text = """
REDLINE Quick Help

LAZY LOADING:
• Automatically processes large datasets in batches
• Activates for >50 files
• Prevents memory issues
• Shows real-time progress

KEY FEATURES:
• Virtual scrolling for large datasets
• Advanced query builder
• Multiple file format support
• Technical indicators
• Batch processing

SHORTCUTS:
• Ctrl+O: Open files
• Ctrl+S: Save data
• F1: Show this help
• Ctrl+Q: Quit application

For detailed help, use the full User Manual.
    """
    
    text_widget = scrolledtext.ScrolledText(
        help_window,
        wrap=tk.WORD,
        width=70,
        height=20,
        font=('Arial', 10)
    )
    text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    text_widget.insert(tk.END, help_text)
    text_widget.config(state=tk.DISABLED)
    
    close_button = ttk.Button(help_window, text="Close", command=help_window.destroy)
    close_button.pack(pady=10)
    
    return help_window
