import tkinter as tk
from tkinter import ttk
import pandas as pd
import os
from data_module import DataLoader
from data_module_shared import DatabaseConnector, StockAnalyzerGUI

def main():
    # Create the root window
    root = tk.Tk()
    
    # Initialize components
    loader = DataLoader()
    connector = DatabaseConnector()
    
    # Create the main application
    app = StockAnalyzerGUI(root, loader, connector)
    
    # Start the application
    root.mainloop()

if __name__ == "__main__":
    main() 