#!/usr/bin/env python3
"""
Grid layout utilities for REDLINE GUI components.
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional


class GridLayoutManager:
    """Manager for consistent grid layouts across the application"""
    
    def __init__(self):
        """Initialize grid layout manager"""
        self.layout_configs = {
            'main_window': {
                'rows': [(0, {'weight': 1})],
                'columns': [(0, {'weight': 1})]
            },
            'notebook': {
                'sticky': 'nsew',
                'padding': {'padx': 10, 'pady': 10}
            },
            'data_loader_tab': {
                'rows': [(0, {'weight': 1}), (1, {'weight': 0})],
                'columns': [(0, {'weight': 1})]
            },
            'file_selection_group': {
                'rows': [(1, {'weight': 1})],
                'columns': [(0, {'weight': 1})],
                'sticky': 'nsew',
                'padding': {'padx': 5, 'pady': 5}
            },
            'data_view_tab': {
                'rows': [(0, {'weight': 0}), (1, {'weight': 1})],
                'columns': [(0, {'weight': 1})]
            },
            'data_display_group': {
                'rows': [(0, {'weight': 1})],
                'columns': [(0, {'weight': 1})],
                'sticky': 'nsew',
                'padding': {'padx': 5, 'pady': 5}
            }
        }
    
    def configure_widget(self, widget: tk.Widget, config_name: str):
        """
        Configure widget grid layout using predefined configuration.
        
        Args:
            widget: Widget to configure
            config_name: Name of configuration to apply
        """
        if config_name not in self.layout_configs:
            raise ValueError(f"Unknown layout configuration: {config_name}")
        
        config = self.layout_configs[config_name]
        
        # Configure rows
        if 'rows' in config:
            for row_idx, row_config in config['rows']:
                widget.grid_rowconfigure(row_idx, **row_config)
        
        # Configure columns
        if 'columns' in config:
            for col_idx, col_config in config['columns']:
                widget.grid_columnconfigure(col_idx, **col_config)
    
    def grid_widget(self, widget: tk.Widget, config_name: str, **kwargs):
        """
        Place widget in grid using predefined configuration.
        
        Args:
            widget: Widget to place
            config_name: Name of configuration to use
            **kwargs: Additional grid parameters
        """
        if config_name not in self.layout_configs:
            raise ValueError(f"Unknown layout configuration: {config_name}")
        
        config = self.layout_configs[config_name]
        
        # Merge configuration with provided kwargs
        grid_kwargs = {}
        if 'sticky' in config:
            grid_kwargs['sticky'] = config['sticky']
        if 'padding' in config:
            grid_kwargs.update(config['padding'])
        
        grid_kwargs.update(kwargs)
        widget.grid(**grid_kwargs)


class TabLayoutBuilder:
    """Builder for creating consistent tab layouts"""
    
    def __init__(self, notebook: ttk.Notebook):
        """
        Initialize tab layout builder.
        
        Args:
            notebook: Notebook widget to add tabs to
        """
        self.notebook = notebook
        self.layout_manager = GridLayoutManager()
    
    def create_tab(self, name: str, layout_config: str = 'data_loader_tab') -> ttk.Frame:
        """
        Create a new tab with consistent layout.
        
        Args:
            name: Tab name
            layout_config: Layout configuration to use
            
        Returns:
            Created tab frame
        """
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=name)
        
        # Configure tab layout
        self.layout_manager.configure_widget(tab_frame, layout_config)
        
        return tab_frame
    
    def create_labeled_group(self, parent: tk.Widget, title: str, 
                           layout_config: str = 'file_selection_group') -> ttk.LabelFrame:
        """
        Create a labeled frame group with consistent layout.
        
        Args:
            parent: Parent widget
            title: Group title
            layout_config: Layout configuration to use
            
        Returns:
            Created labeled frame
        """
        group = ttk.LabelFrame(parent, text=title)
        
        # Configure group layout
        self.layout_manager.configure_widget(group, layout_config)
        self.layout_manager.grid_widget(group, layout_config)
        
        return group
    
    def create_button_row(self, parent: tk.Widget, buttons: list) -> ttk.Frame:
        """
        Create a row of buttons with consistent spacing.
        
        Args:
            parent: Parent widget
            buttons: List of button configurations [{'text': str, 'command': callable}, ...]
            
        Returns:
            Frame containing buttons
        """
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        
        for i, button_config in enumerate(buttons):
            btn = ttk.Button(button_frame, **button_config)
            btn.grid(row=0, column=i, padx=5)
        
        return button_frame


class DataDisplayLayout:
    """Layout utilities for data display components"""
    
    @staticmethod
    def create_scrollable_listbox(parent: tk.Widget, **kwargs) -> tuple:
        """
        Create a scrollable listbox with consistent layout.
        
        Args:
            parent: Parent widget
            **kwargs: Additional listbox parameters
            
        Returns:
            Tuple of (listbox, scrollbar, frame)
        """
        # Create frame for listbox and scrollbar
        listbox_frame = ttk.Frame(parent)
        listbox_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        listbox_frame.grid_columnconfigure(0, weight=1)
        listbox_frame.grid_rowconfigure(0, weight=1)
        
        # Create listbox
        listbox = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE, **kwargs)
        listbox.grid(row=0, column=0, sticky='nsew')
        
        # Create scrollbar
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        listbox.config(yscrollcommand=scrollbar.set)
        
        return listbox, scrollbar, listbox_frame
    
    @staticmethod
    def create_progress_section(parent: tk.Widget) -> tuple:
        """
        Create progress bar section with consistent layout.
        
        Args:
            parent: Parent widget
            
        Returns:
            Tuple of (progress_bar, status_label)
        """
        # Progress frame
        progress_frame = ttk.Frame(parent)
        progress_frame.grid(row=2, column=0, sticky='ew', padx=5, pady=5)
        
        # Status label
        status_label = ttk.Label(progress_frame, text="Ready")
        status_label.grid(row=0, column=0, padx=5, pady=2)
        
        # Progress bar
        progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        progress_bar.grid(row=1, column=0, padx=5, pady=2)
        
        return progress_bar, status_label


class FormLayoutBuilder:
    """Builder for creating form layouts"""
    
    def __init__(self, parent: tk.Widget):
        """
        Initialize form layout builder.
        
        Args:
            parent: Parent widget for the form
        """
        self.parent = parent
        self.row = 0
    
    def add_labeled_entry(self, label_text: str, variable: tk.Variable, 
                         width: int = 20) -> ttk.Entry:
        """
        Add a labeled entry field to the form.
        
        Args:
            label_text: Label text
            variable: Variable to bind to entry
            width: Entry width
            
        Returns:
            Created entry widget
        """
        # Label
        label = ttk.Label(self.parent, text=label_text)
        label.grid(row=self.row, column=0, sticky='w', padx=5, pady=5)
        
        # Entry
        entry = ttk.Entry(self.parent, textvariable=variable, width=width)
        entry.grid(row=self.row, column=1, sticky='ew', padx=5, pady=5)
        
        self.row += 1
        return entry
    
    def add_labeled_combobox(self, label_text: str, variable: tk.Variable, 
                           values: list, width: int = 20) -> ttk.Combobox:
        """
        Add a labeled combobox to the form.
        
        Args:
            label_text: Label text
            variable: Variable to bind to combobox
            values: Combobox values
            width: Combobox width
            
        Returns:
            Created combobox widget
        """
        # Label
        label = ttk.Label(self.parent, text=label_text)
        label.grid(row=self.row, column=0, sticky='w', padx=5, pady=5)
        
        # Combobox
        combobox = ttk.Combobox(self.parent, textvariable=variable, values=values, width=width)
        combobox.grid(row=self.row, column=1, sticky='ew', padx=5, pady=5)
        
        self.row += 1
        return combobox
    
    def add_button(self, text: str, command, column: int = 0) -> ttk.Button:
        """
        Add a button to the form.
        
        Args:
            text: Button text
            command: Button command
            column: Column to place button in
            
        Returns:
            Created button widget
        """
        button = ttk.Button(self.parent, text=text, command=command)
        button.grid(row=self.row, column=column, padx=5, pady=5)
        
        self.row += 1
        return button
    
    def configure_columns(self, weights: list):
        """
        Configure column weights for the form.
        
        Args:
            weights: List of column weights
        """
        for i, weight in enumerate(weights):
            self.parent.grid_columnconfigure(i, weight=weight)
