#!/usr/bin/env python3
"""
Data source classes for lazy loading and virtual scrolling.
"""

import pandas as pd
import duckdb
from typing import List


class DataSource:
    """Abstract data source for virtual scrolling"""
    
    def __init__(self, file_path: str, format_type: str):
        """
        Initialize data source.
        
        Args:
            file_path: Path to data file
            format_type: Type of data file ('duckdb', 'csv', etc.)
        """
        self.file_path = file_path
        self.format_type = format_type
        self.connection = None
        self.total_rows = 0
        self._initialize()
        
    def _initialize(self):
        """Initialize the data source"""
        if self.format_type == 'duckdb':
            self.connection = duckdb.connect(self.file_path)
            self.total_rows = self.connection.execute("SELECT COUNT(*) FROM tickers_data").fetchone()[0]
        else:
            # For other formats, load into memory (not ideal for large files)
            from data_loader import DataLoader
            df = DataLoader.load_file_by_type(self.file_path, self.format_type)
            if isinstance(df, pd.DataFrame):
                self.data = df
                self.total_rows = len(df)
            else:
                # Convert other formats to pandas
                import polars as pl
                import pyarrow as pa
                if isinstance(df, pl.DataFrame):
                    self.data = df.to_pandas()
                elif isinstance(df, pa.Table):
                    self.data = df.to_pandas()
                else:
                    self.data = pd.DataFrame()
                self.total_rows = len(self.data)
                
    def get_total_rows(self):
        """Get total number of rows"""
        return self.total_rows
        
    def get_row(self, index: int):
        """Get a specific row by index"""
        if self.format_type == 'duckdb':
            query = f"SELECT * FROM tickers_data LIMIT 1 OFFSET {index}"
            result = self.connection.execute(query).fetchone()
            return list(result) if result else []
        else:
            if index < len(self.data):
                return list(self.data.iloc[index])
            return []
            
    def get_rows(self, start: int, end: int):
        """Get a range of rows"""
        if self.format_type == 'duckdb':
            query = f"SELECT * FROM tickers_data LIMIT {end - start} OFFSET {start}"
            result = self.connection.execute(query).fetchdf()
            return [list(row) for _, row in result.iterrows()]
        else:
            return [list(row) for _, row in self.data.iloc[start:end].iterrows()]
            
    def close(self):
        """Close the data source"""
        if self.connection:
            self.connection.close()


class DatabaseConnector:
    """Database connection manager"""
    
    def __init__(self, db_path: str = 'redline_data.duckdb'):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """Connect to database"""
        if not self.connection:
            self.connection = duckdb.connect(self.db_path)
        return self.connection
    
    def disconnect(self):
        """Disconnect from database"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def execute_query(self, query: str, params: tuple = None):
        """Execute a query and return results"""
        if not self.connection:
            self.connect()
        
        if params:
            return self.connection.execute(query, params).fetchall()
        else:
            return self.connection.execute(query).fetchall()
    
    def execute_dataframe(self, query: str, params: tuple = None):
        """Execute a query and return DataFrame"""
        if not self.connection:
            self.connect()
        
        if params:
            return self.connection.execute(query, params).fetchdf()
        else:
            return self.connection.execute(query).fetchdf()
    
    def get_table_info(self, table_name: str = 'tickers_data'):
        """Get information about a table"""
        if not self.connection:
            self.connect()
        
        # Get column information
        columns_query = f"DESCRIBE {table_name}"
        columns = self.execute_query(columns_query)
        
        # Get row count
        count_query = f"SELECT COUNT(*) FROM {table_name}"
        count = self.execute_query(count_query)[0][0]
        
        return {
            'columns': columns,
            'row_count': count
        }
