#!/usr/bin/env python3
"""
Main entry point for the refactored REDLINE application.
"""

import tkinter as tk
import logging
from data_loader import DataLoader
from data_sources import DatabaseConnector
from data_adapter import DataAdapter
from gui_main import StockAnalyzerGUI
from user_manual import show_user_manual_popup


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('redline.log'),
            logging.StreamHandler()
        ]
    )


def main():
    """Main entry point"""
    # Setup logging
    setup_logging()
    
    try:
        # Create the root window
        root = tk.Tk()
        root.title("REDLINE - Financial Data Processor")
        
        # Initialize components
        loader = DataLoader()
        connector = DatabaseConnector()
        adapter = DataAdapter()
        
        # Create the main application
        app = StockAnalyzerGUI(root, loader, connector)
        
        # Add help menu
        menubar = tk.Menu(root)
        root.config(menu=menubar)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="User Manual", command=lambda: show_user_manual_popup(root))
        help_menu.add_command(label="About", command=lambda: show_about_dialog(root))
        
        # Start the application
        logging.info("Starting REDLINE application")
        root.mainloop()
        
    except Exception as e:
        logging.error(f"Failed to start application: {str(e)}")
        print(f"Error: {str(e)}")


def show_about_dialog(parent):
    """Show about dialog"""
    about_window = tk.Toplevel(parent)
    about_window.title("About REDLINE")
    about_window.geometry("400x300")
    
    about_text = """
REDLINE - Financial Data Processor
Version 2.0 (Refactored with Lazy Loading)

Features:
• Lazy loading for large datasets (10,000+ files)
• Virtual scrolling for efficient data viewing
• Advanced query builder with SQL-like syntax
• Multiple file format support
• Batch processing with progress tracking
• Technical indicators and data analysis

Architecture:
• Modular design with ~200 LOC per file
• Clean separation of concerns
• Efficient memory management
• Robust error handling

Built with Python, tkinter, pandas, and DuckDB.
    """
    
    text_widget = tk.Text(about_window, wrap=tk.WORD, width=50, height=15)
    text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    text_widget.insert(tk.END, about_text)
    text_widget.config(state=tk.DISABLED)
    
    close_button = tk.Button(about_window, text="Close", command=about_window.destroy)
    close_button.pack(pady=10)


if __name__ == "__main__":
    main()
