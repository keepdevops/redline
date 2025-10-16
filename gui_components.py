#!/usr/bin/env python3
"""
GUI components for virtual scrolling and advanced query building.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Any, Callable, Optional


class VirtualScrollingTreeview:
    """A virtual scrolling TreeView that only loads visible items into memory"""
    
    def __init__(self, parent, columns: List[str], **kwargs):
        """
        Initialize virtual scrolling treeview.
        
        Args:
            parent: Parent widget
            columns: List of column names
            **kwargs: Additional arguments for Treeview
        """
        self.parent = parent
        self.columns = columns
        self.tree = ttk.Treeview(parent, columns=columns, **kwargs)
        
        # Virtual scrolling state
        self.total_rows = 0
        self.visible_start = 0
        self.visible_end = 0
        self.row_height = 20  # Approximate row height
        self.visible_count = 0
        self.data_source = None
        self.cached_data = {}
        self.cache_size = 1000  # Number of rows to cache
        
        # Bind scroll events
        self.tree.bind('<Configure>', self._on_configure)
        self.tree.bind('<MouseWheel>', self._on_scroll)
        
    def _on_configure(self, event):
        """Handle window resize to recalculate visible items"""
        self._update_visible_range()
        
    def _on_scroll(self, event):
        """Handle scroll events to update visible items"""
        self._update_visible_range()
        
    def _update_visible_range(self):
        """Calculate which rows should be visible"""
        if not self.data_source:
            return
            
        # Calculate visible range based on scroll position
        scroll_pos = self.tree.yview()
        visible_start = int(scroll_pos[0] * self.total_rows)
        visible_end = int(scroll_pos[1] * self.total_rows)
        
        if visible_start != self.visible_start or visible_end != self.visible_end:
            self.visible_start = visible_start
            self.visible_end = visible_end
            self._load_visible_items()
    
    def _load_visible_items(self):
        """Load only the visible items into the treeview"""
        if not self.data_source:
            return
            
        # Clear current items
        self.tree.delete(*self.tree.get_children())
        
        # Load visible items
        for i in range(self.visible_start, min(self.visible_end + 1, self.total_rows)):
            if i in self.cached_data:
                row_data = self.cached_data[i]
            else:
                row_data = self.data_source.get_row(i)
                if len(self.cached_data) < self.cache_size:
                    self.cached_data[i] = row_data
                    
            self.tree.insert('', 'end', values=row_data)
    
    def set_data_source(self, data_source):
        """Set the data source for virtual scrolling"""
        self.data_source = data_source
        self.total_rows = data_source.get_total_rows()
        self._update_visible_range()
        
    def refresh(self):
        """Refresh the display"""
        self._update_visible_range()


class AdvancedQueryBuilder:
    """Advanced query builder for complex data filtering"""
    
    def __init__(self, parent):
        """Initialize query builder"""
        self.parent = parent
        self.conditions = []
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the query builder UI"""
        # Main frame
        self.frame = ttk.Frame(self.parent)
        
        # Column selection
        ttk.Label(self.frame, text="Column:").grid(row=0, column=0, padx=5, pady=5)
        self.column_var = tk.StringVar()
        self.column_combo = ttk.Combobox(self.frame, textvariable=self.column_var, width=20)
        self.column_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # Operator selection
        ttk.Label(self.frame, text="Operator:").grid(row=0, column=2, padx=5, pady=5)
        self.operator_var = tk.StringVar()
        self.operator_combo = ttk.Combobox(self.frame, textvariable=self.operator_var, width=15)
        self.operator_combo['values'] = [
            'equals', 'not_equals', 'contains', 'not_contains',
            'greater_than', 'less_than', 'greater_equal', 'less_equal',
            'between', 'in', 'not_in', 'is_null', 'is_not_null'
        ]
        self.operator_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Value input
        ttk.Label(self.frame, text="Value:").grid(row=0, column=4, padx=5, pady=5)
        self.value_entry = ttk.Entry(self.frame, width=20)
        self.value_entry.grid(row=0, column=5, padx=5, pady=5)
        
        # Add condition button
        add_btn = ttk.Button(self.frame, text="Add Condition", command=self.add_condition)
        add_btn.grid(row=0, column=6, padx=5, pady=5)
        
        # Conditions list
        ttk.Label(self.frame, text="Conditions:").grid(row=1, column=0, columnspan=7, sticky='w', padx=5, pady=(10,5))
        self.conditions_listbox = tk.Listbox(self.frame, height=8)
        self.conditions_listbox.grid(row=2, column=0, columnspan=7, sticky='ew', padx=5, pady=5)
        
        # Remove condition button
        remove_btn = ttk.Button(self.frame, text="Remove Selected", command=self.remove_condition)
        remove_btn.grid(row=3, column=0, padx=5, pady=5)
        
        # Clear all button
        clear_btn = ttk.Button(self.frame, text="Clear All", command=self.clear_conditions)
        clear_btn.grid(row=3, column=1, padx=5, pady=5)
        
        # Apply query button
        apply_btn = ttk.Button(self.frame, text="Apply Query", command=self.apply_query)
        apply_btn.grid(row=3, column=2, padx=5, pady=5)
        
        # Configure grid weights
        self.frame.grid_columnconfigure(7, weight=1)
    
    def set_columns(self, columns: List[str]):
        """Set available columns for the query builder"""
        self.column_combo['values'] = columns
        if columns:
            self.column_combo.set(columns[0])
    
    def add_condition(self):
        """Add a new condition to the query"""
        column = self.column_var.get()
        operator = self.operator_var.get()
        value = self.value_entry.get()
        
        if not all([column, operator]):
            return
        
        condition = {
            'column': column,
            'operator': operator,
            'value': value
        }
        
        self.conditions.append(condition)
        self._update_conditions_display()
        
        # Clear inputs
        self.value_entry.delete(0, tk.END)
    
    def remove_condition(self):
        """Remove selected condition"""
        selection = self.conditions_listbox.curselection()
        if selection:
            index = selection[0]
            del self.conditions[index]
            self._update_conditions_display()
    
    def clear_conditions(self):
        """Clear all conditions"""
        self.conditions = []
        self._update_conditions_display()
    
    def _update_conditions_display(self):
        """Update the conditions listbox display"""
        self.conditions_listbox.delete(0, tk.END)
        for condition in self.conditions:
            display_text = f"{condition['column']} {condition['operator']} {condition['value']}"
            self.conditions_listbox.insert(tk.END, display_text)
    
    def build_query(self, conditions: List[Dict], table_name: str = 'tickers_data') -> tuple:
        """Build SQL query from conditions"""
        if not conditions:
            return f"SELECT * FROM {table_name}", ()
        
        where_clauses = []
        params = []
        
        for condition in conditions:
            column = condition['column']
            operator = condition['operator']
            value = condition['value']
            
            if operator == 'equals':
                where_clauses.append(f"{column} = ?")
                params.append(value)
            elif operator == 'not_equals':
                where_clauses.append(f"{column} != ?")
                params.append(value)
            elif operator == 'contains':
                where_clauses.append(f"{column} LIKE ?")
                params.append(f"%{value}%")
            elif operator == 'not_contains':
                where_clauses.append(f"{column} NOT LIKE ?")
                params.append(f"%{value}%")
            elif operator == 'greater_than':
                where_clauses.append(f"{column} > ?")
                params.append(float(value))
            elif operator == 'less_than':
                where_clauses.append(f"{column} < ?")
                params.append(float(value))
            elif operator == 'greater_equal':
                where_clauses.append(f"{column} >= ?")
                params.append(float(value))
            elif operator == 'less_equal':
                where_clauses.append(f"{column} <= ?")
                params.append(float(value))
            elif operator == 'between':
                # Expect value to be comma-separated
                values = value.split(',')
                if len(values) == 2:
                    where_clauses.append(f"{column} BETWEEN ? AND ?")
                    params.extend([float(values[0]), float(values[1])])
            elif operator == 'in':
                # Expect value to be comma-separated
                values = [v.strip() for v in value.split(',')]
                placeholders = ','.join(['?' for _ in values])
                where_clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)
            elif operator == 'not_in':
                values = [v.strip() for v in value.split(',')]
                placeholders = ','.join(['?' for _ in values])
                where_clauses.append(f"{column} NOT IN ({placeholders})")
                params.extend(values)
            elif operator == 'is_null':
                where_clauses.append(f"{column} IS NULL")
            elif operator == 'is_not_null':
                where_clauses.append(f"{column} IS NOT NULL")
        
        query = f"SELECT * FROM {table_name} WHERE {' AND '.join(where_clauses)}"
        return query, tuple(params)
    
    def apply_query(self):
        """Apply the built query (to be implemented by parent)"""
        # This should be overridden by the parent class
        pass
