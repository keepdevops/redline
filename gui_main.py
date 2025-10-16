#!/usr/bin/env python3
"""
Main GUI class for REDLINE data processing application.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import logging
from typing import List, Optional

from data_loader import DataLoader
from data_sources import DatabaseConnector
from lazy_loader import LazyFileLoader
from gui_components import VirtualScrollingTreeview, AdvancedQueryBuilder


class StockAnalyzerGUI:
    """Main GUI application for stock data analysis"""
    
    def __init__(self, root: tk.Tk, loader: DataLoader, connector: DatabaseConnector):
        """Initialize the main GUI"""
        self.root = root
        self.loader = loader
        self.connector = connector
        
        self.root.title("REDLINE Data Conversion Utility")
        self.root.minsize(1200, 800)
        
        # Configure root grid
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Setup notebook with tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
        
        self.setup_tabs()
        self.setup_variables()
        
    def setup_variables(self):
        """Setup tkinter variables"""
        self.input_format = tk.StringVar(value='txt')
        self.output_format = tk.StringVar(value='duckdb')
        self.progress_var = tk.DoubleVar()
        self.current_file_path = None
        
    def setup_tabs(self):
        """Setup the main tabs"""
        # Data Loader Tab
        self.setup_data_loader_tab()
        
        # Data Viewer Tab
        self.setup_data_viewer_tab()
        
    def setup_data_loader_tab(self):
        """Setup the data loader tab"""
        loader_frame = ttk.Frame(self.notebook)
        self.notebook.add(loader_frame, text='Data Loader')
        
        # File selection section
        file_group = ttk.LabelFrame(loader_frame, text="File Selection")
        file_group.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        file_group.grid_columnconfigure(0, weight=1)
        file_group.grid_rowconfigure(1, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(file_group)
        button_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        
        ttk.Button(button_frame, text="Browse Files", command=self.browse_files).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Select All", command=self.select_all_files).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Deselect All", command=self.deselect_all_files).grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="Process Selected", command=self.process_selected_files).grid(row=0, column=3, padx=5)
        
        # File listbox
        listbox_frame = ttk.Frame(file_group)
        listbox_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        listbox_frame.grid_columnconfigure(0, weight=1)
        listbox_frame.grid_rowconfigure(0, weight=1)
        
        self.input_listbox = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE)
        self.input_listbox.grid(row=0, column=0, sticky='nsew')
        
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.input_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.input_listbox.config(yscrollcommand=scrollbar.set)
        
        # Format selection
        format_frame = ttk.LabelFrame(loader_frame, text="Format Selection")
        format_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
        
        ttk.Label(format_frame, text="Input Format:").grid(row=0, column=0, padx=5, pady=5)
        input_combo = ttk.Combobox(format_frame, textvariable=self.input_format, 
                                  values=['txt', 'csv', 'json', 'parquet', 'feather'])
        input_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(format_frame, text="Output Format:").grid(row=0, column=2, padx=5, pady=5)
        output_combo = ttk.Combobox(format_frame, textvariable=self.output_format,
                                   values=['duckdb', 'csv', 'json', 'parquet', 'feather'])
        output_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(loader_frame, variable=self.progress_var, 
                                          mode='determinate', length=400)
        
        # Configure grid weights
        loader_frame.grid_rowconfigure(0, weight=1)
        loader_frame.grid_columnconfigure(0, weight=1)
        
    def setup_data_viewer_tab(self):
        """Setup the data viewer tab"""
        viewer_frame = ttk.Frame(self.notebook)
        self.notebook.add(viewer_frame, text='Data Viewer')
        
        # File selection for viewing
        file_frame = ttk.LabelFrame(viewer_frame, text="Select File to View")
        file_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        
        ttk.Button(file_frame, text="Browse File", command=self.browse_view_file).grid(row=0, column=0, padx=5, pady=5)
        self.view_file_label = ttk.Label(file_frame, text="No file selected")
        self.view_file_label.grid(row=0, column=1, padx=5, pady=5)
        
        # Data display
        data_frame = ttk.LabelFrame(viewer_frame, text="Data")
        data_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        
        # Use virtual scrolling treeview
        self.data_tree = VirtualScrollingTreeview(data_frame, 
                                                 columns=['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'vol'])
        self.data_tree.tree.grid(row=0, column=0, sticky='nsew')
        
        # Configure grid weights
        viewer_frame.grid_rowconfigure(1, weight=1)
        viewer_frame.grid_columnconfigure(0, weight=1)
        data_frame.grid_rowconfigure(0, weight=1)
        data_frame.grid_columnconfigure(0, weight=1)
        
    def browse_files(self):
        """Browse for input files"""
        filetypes = [
            ('All supported', '*.txt;*.csv;*.json;*.parquet;*.feather'),
            ('Text files', '*.txt'),
            ('CSV files', '*.csv'),
            ('JSON files', '*.json'),
            ('Parquet files', '*.parquet'),
            ('Feather files', '*.feather'),
            ('All files', '*.*')
        ]
        
        files = filedialog.askopenfilenames(title="Select files to process", filetypes=filetypes)
        
        if files:
            self.input_listbox.delete(0, tk.END)
            for file in files:
                # Show file size and last modified
                size = os.path.getsize(file)
                self.input_listbox.insert(tk.END, f"{file} [{size:,} bytes]")
    
    def browse_view_file(self):
        """Browse for file to view"""
        filetypes = [
            ('All supported', '*.duckdb;*.csv;*.json;*.parquet;*.feather'),
            ('DuckDB files', '*.duckdb'),
            ('CSV files', '*.csv'),
            ('JSON files', '*.json'),
            ('Parquet files', '*.parquet'),
            ('Feather files', '*.feather')
        ]
        
        file = filedialog.askopenfilename(title="Select file to view", filetypes=filetypes)
        
        if file:
            self.current_file_path = file
            self.view_file_label.config(text=os.path.basename(file))
            self.load_file_for_viewing(file)
    
    def select_all_files(self):
        """Select all files in the listbox"""
        self.input_listbox.selection_set(0, tk.END)
    
    def deselect_all_files(self):
        """Deselect all files in the listbox"""
        self.input_listbox.selection_clear(0, tk.END)
    
    def process_selected_files(self):
        """Process the selected files"""
        selections = self.input_listbox.curselection()
        if not selections:
            messagebox.showerror("Error", "No files selected")
            return
        
        file_paths = [self.input_listbox.get(idx).split(' [')[0] for idx in selections]
        
        # Show progress bar
        self.progress_bar.grid(row=2, column=0, pady=10)
        self.progress_var.set(0)
        
        # Process files in background thread
        def worker():
            try:
                input_format = self.input_format.get()
                output_format = self.output_format.get()
                
                # Check if we should use lazy loading for large datasets
                if len(file_paths) > 50:  # Use lazy loading for more than 50 files
                    print(f"Using lazy loading for {len(file_paths)} files...")
                    
                    # Create temporary DuckDB file for lazy processing
                    temp_db_path = "temp_lazy_processing.duckdb"
                    
                    # Progress callback for lazy loading
                    def lazy_progress_callback(batch_idx, file_progress):
                        total_batches = lazy_loader.get_batch_count()
                        batch_progress = (batch_idx / total_batches) * 40  # 40% for processing
                        file_progress_in_batch = (file_progress / total_batches) * 40
                        total_progress = 30 + batch_progress + file_progress_in_batch
                        self.root.after(0, lambda: self.progress_var.set(total_progress))
                    
                    # Create lazy loader
                    lazy_loader = LazyFileLoader(file_paths, batch_size=100)
                    
                    # Process all batches
                    total_processed = lazy_loader.process_all_batches(
                        temp_db_path, 
                        input_format, 
                        lazy_progress_callback
                    )
                    
                    if total_processed == 0:
                        self.root.after(0, lambda: messagebox.showerror("Error", "No valid data loaded"))
                        return
                    
                    # Save final result
                    self.root.after(0, lambda: self.progress_var.set(90))
                    self.save_processed_data(temp_db_path, output_format)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_db_path):
                        os.remove(temp_db_path)
                        
                    print(f"Lazy loading completed: {total_processed} files processed")
                    
                else:
                    # Use original method for small datasets
                    self.process_small_dataset(file_paths, input_format, output_format)
                
                self.root.after(0, lambda: self.progress_var.set(100))
                self.root.after(0, lambda: messagebox.showinfo("Success", "Processing completed successfully!"))
                
            except Exception as e:
                logging.error(f"Processing failed: {str(e)}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self.progress_bar.grid_remove())
        
        threading.Thread(target=worker, daemon=True).start()
    
    def process_small_dataset(self, file_paths: List[str], input_format: str, output_format: str):
        """Process small datasets using traditional method"""
        # Implementation for small datasets (existing logic)
        pass
    
    def save_processed_data(self, temp_db_path: str, output_format: str):
        """Save processed data to final format"""
        # Implementation for saving processed data
        pass
    
    def load_file_for_viewing(self, file_path: str):
        """Load file for viewing in the data viewer"""
        try:
            # Determine file format
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.duckdb':
                format_type = 'duckdb'
            elif ext == '.csv':
                format_type = 'csv'
            elif ext == '.json':
                format_type = 'json'
            elif ext == '.parquet':
                format_type = 'parquet'
            elif ext == '.feather':
                format_type = 'feather'
            else:
                format_type = 'csv'
            
            # Create data source and connect to virtual scrolling treeview
            from data_sources import DataSource
            data_source = DataSource(file_path, format_type)
            self.data_tree.set_data_source(data_source)
            
        except Exception as e:
            logging.error(f"Failed to load file for viewing: {str(e)}")
            messagebox.showerror("Error", f"Failed to load file: {str(e)}")
    
    def run_in_main_thread(self, func, *args, **kwargs):
        """Run function in main thread"""
        self.root.after(0, lambda: func(*args, **kwargs))
