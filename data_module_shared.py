#!/usr/bin/env python3
"""REDLINE module for stock market data management in a Docker/Podman container."""

import logging
import sys
import configparser
import pandas as pd
import polars as pl
import pyarrow as pa
import duckdb
import sqlalchemy
from sqlalchemy import create_engine
import tensorflow as tf
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.simpledialog import askstring
from typing import Union, List, Dict
import argparse
import os
import traceback
import tkinter.font as tkFont
from sklearn.preprocessing import MinMaxScaler, StandardScaler
import numpy as np
import threading
from data_user_manual import show_user_manual_popup
import sqlite3
from datetime import datetime, timedelta
import re
from typing import Optional, Dict, List, Tuple, Any, Union
import weakref

# Configure logging
logging.basicConfig(filename='redline.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataLoader:
    SCHEMA = ['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'vol', 'openint', 'format']
    EXT_TO_FORMAT = {
        '.csv': 'csv',
        '.txt': 'txt',
        '.json': 'json',
        '.duckdb': 'duckdb',
        '.parquet': 'parquet',
        '.feather': 'feather',
        '.h5': 'keras'
    }
    # Centralized mapping for file dialog info: format -> (extension, description, pattern)
    FORMAT_DIALOG_INFO = {
        'csv':     ('.csv',     'CSV Files', '*.csv'),
        'txt':     ('.txt',     'TXT Files', '*.txt'),
        'json':    ('.json',    'JSON Files', '*.json'),
        'duckdb':  ('.duckdb',  'DuckDB Files', '*.duckdb'),
        'parquet': ('.parquet', 'Parquet Files', '*.parquet'),
        'feather': ('.feather', 'Feather Files', '*.feather'),
        'keras':   ('.h5',      'Keras Model', '*.h5'),
        'tensorflow': ('.npz',  'NumPy Zip', '*.npz')
    }

    @staticmethod
    def clean_and_select_columns(data: pd.DataFrame) -> pd.DataFrame:
        try:
            # Make a copy to avoid modifying original
            data = data.copy()
            
            # Ensure all schema columns are present
            for col in DataLoader.SCHEMA:
                if col not in data.columns:
                    data[col] = None
            
            # Select only schema columns in correct order
            data = data[DataLoader.SCHEMA]
            
            # Clean numeric columns and handle type conversion safely
            numeric_cols = ['open', 'high', 'low', 'close', 'vol', 'openint']
            for col in numeric_cols:
                if col in data.columns:
                    # Convert to numeric, coerce errors to NaN
                    data[col] = pd.to_numeric(data[col], errors='coerce')
                    
                    # Clean any remaining non-numeric values
                    data[col] = data[col].apply(
                        lambda x: float(x) if pd.notnull(x) and not isinstance(x, (list, tuple, dict)) else None
                    )
            
            # Ensure timestamp is datetime
            if 'timestamp' in data.columns:
                data['timestamp'] = pd.to_datetime(data['timestamp'], errors='coerce')
                
            return data
        except Exception as e:
            logging.error(f"Error in clean_and_select_columns: {str(e)}")
            raise

    def __init__(self, config_path: str = 'data_config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.db_path = self.config['Data'].get('db_path', '/app/redline_data.duckdb')
        self.csv_dir = self.config['Data'].get('csv_dir', '/app/data')
        self.json_dir = self.config['Data'].get('json_dir', '/app/data/json')
        self.parquet_dir = self.config['Data'].get('parquet_dir', '/app/data/parquet')

    def validate_data(self, file_path: str, format: str) -> bool:
        try:
            if format == 'txt':
                # Read the first few lines to check format
                with open(file_path, 'r') as f:
                    header = f.readline().strip()
                    
                # Check for Stooq format header
                required_cols = ['<TICKER>', '<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>']
                header_cols = [col.strip() for col in header.split(',')]
                
                # Validate header columns
                missing_cols = [col for col in required_cols if col not in header_cols]
                if missing_cols:
                    logging.warning(f"Missing required columns in {file_path}: {', '.join(missing_cols)}")
                    return False
                    
                return True
                
            elif format in ['csv', 'json']:
                df = pd.read_csv(file_path) if format == 'csv' else pd.read_json(file_path)
                required = ['ticker', 'timestamp', 'close']
                return all(col in df.columns for col in required)
                
            return True  # For other formats like feather
            
        except Exception as e:
            logging.error(f"Validation failed for {file_path}: {str(e)}")
            return False

    def load_data(self, file_paths: List[str], format: str, delete_empty: bool = False) -> List[Union[pd.DataFrame, pl.DataFrame, pa.Table]]:
        data = []
        skipped_files = []
        
        for path in file_paths:
            try:
                # Convert absolute path to relative path if needed
                relative_path = path.replace('/app/', '')
                
                # Validate file before attempting to load
                if not self.validate_data(relative_path, format):
                    skipped_files.append({
                        'file': os.path.basename(path),
                        'reason': 'Failed validation'
                    })
                    continue
                
                # Load and standardize the data
                df = pd.read_csv(relative_path)
                df = self._standardize_txt_columns(df)
                
                # Validate required columns after standardization
                if not all(col in df.columns for col in ['ticker', 'timestamp', 'close']):
                    skipped_files.append({
                        'file': os.path.basename(path),
                        'reason': 'Missing required columns after standardization'
                    })
                    continue
                
                data.append(df)
                logging.info(f"Successfully loaded {path}")
                
            except Exception as e:
                logging.error(f"Failed to load {path}: {str(e)}")
                skipped_files.append({
                    'file': os.path.basename(path),
                    'reason': str(e)
                })
        
        if not data:
            raise ValueError(f"No valid data could be loaded. Skipped files: {', '.join([f['file'] for f in skipped_files])}")
        
        return data

    def convert_format(self, data: Union[pd.DataFrame, pl.DataFrame, pa.Table], from_format: str, to_format: str) -> Union[pd.DataFrame, pl.DataFrame, pa.Table, dict]:
        if from_format == to_format:
            return data
        if isinstance(data, list):
            return [self.convert_format(d, from_format, to_format) for d in data]
        try:
            if from_format == 'pandas':
                if to_format == 'polars':
                    return pl.from_pandas(data)
                elif to_format == 'pyarrow':
                    return pa.Table.from_pandas(data)
            elif from_format == 'polars':
                if to_format == 'pandas':
                    return data.to_pandas()
                elif to_format == 'pyarrow':
                    return data.to_arrow()
            elif from_format == 'pyarrow':
                if to_format == 'pandas':
                    return data.to_pandas()
                elif to_format == 'polars':
                    return pl.from_arrow(data)
            logging.info(f"Converted from {from_format} to {to_format}")
            return data
        except Exception as e:
            logging.error(f"Conversion failed from {from_format} to {to_format}: {str(e)}")
            raise

    def save_to_shared(self, table: str, data: Union[pd.DataFrame, pl.DataFrame, pa.Table], format: str) -> None:
        try:
            # Convert to pandas DataFrame if needed
            if isinstance(data, pl.DataFrame):
                data = data.to_pandas()
            elif isinstance(data, pa.Table):
                data = data.to_pandas()
            data['format'] = format
            data = DataLoader.clean_and_select_columns(data)
            
            # Ensure timestamp is in datetime format
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            
            # Diagnostic: print dtypes and sample values
            print("Column dtypes before saving:")
            print(data.dtypes)
            for col in ['open', 'high', 'low', 'close', 'vol', 'openint']:
                if col in data.columns:
                    print(f"Sample values for {col}:")
                    print(data[col].head(10).to_list())
                
            # Create table if not exists and insert data using DuckDB native
            conn = duckdb.connect(self.db_path)
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table} (
                ticker VARCHAR,
                timestamp TIMESTAMP,  # Changed from VARCHAR to TIMESTAMP
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                vol DOUBLE,
                openint DOUBLE,
                format VARCHAR
            )
            """
            conn.execute(create_table_sql)
            
            # Insert data
            conn.register('temp_df', data)
            insert_sql = f"INSERT INTO {table} SELECT * FROM temp_df"
            conn.execute(insert_sql)
            conn.unregister('temp_df')
            conn.close()
            logging.info(f"Saved data to {table} in format {format}")
        except Exception as e:
            logging.exception(f"Failed to save to {table}: {str(e)}")
            print(f"Failed to save to {table}: {str(e)}")
            raise

    def _standardize_txt_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names and formats for txt files (Stooq format).
        """
        try:
            # Create a copy to avoid modifying the original
            df = df.copy()
            
            # Check required columns - now including <TIME>
            required_cols = ['<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<VOL>']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")
            
            # Create timestamp from DATE and TIME columns
            # Combine date and time (we know <TIME> exists because it's required)
            df['timestamp'] = pd.to_datetime(
                df['<DATE>'].astype(str) + df['<TIME>'].astype(str).str.zfill(6),
                format='%Y%m%d%H%M%S',
                errors='coerce'
            )
            
            # Map the columns directly
            df['ticker'] = df['<TICKER>'] if '<TICKER>' in df.columns else None
            df['open'] = pd.to_numeric(df['<OPEN>'])
            df['high'] = pd.to_numeric(df['<HIGH>'])
            df['low'] = pd.to_numeric(df['<LOW>'])
            df['close'] = pd.to_numeric(df['<CLOSE>'])
            df['vol'] = pd.to_numeric(df['<VOL>'])
            df['openint'] = pd.to_numeric(df['<OPENINT>']) if '<OPENINT>' in df.columns else None
            df['format'] = 'txt'
            
            # Select only the schema columns in the correct order
            df = df[self.SCHEMA]
            
            # Drop rows with missing required values
            df = df.dropna(subset=['timestamp', 'close'])
            
            if df.empty:
                raise ValueError("No valid data after cleaning")
            
            return df
            
        except Exception as e:
            logging.error(f"Error standardizing Stooq columns: {str(e)}")
            raise ValueError(f"Failed to standardize columns: {str(e)}")

    @staticmethod
    def load_file_by_type(file_path, filetype=None):
        import duckdb
        import tensorflow as tf
        import pandas as pd
        import numpy as np
        ext = os.path.splitext(file_path)[1].lower()
        if not filetype:
            filetype = DataLoader.EXT_TO_FORMAT.get(ext, None)
        if filetype == 'csv':
            return pd.read_csv(file_path)
        elif filetype == 'json':
            try:
                return pd.read_json(file_path, lines=True)
            except Exception:
                return pd.read_json(file_path)
        elif filetype == 'txt':
            df = pd.read_csv(file_path, delimiter='\t')
            if df.shape[1] == 1:
                df = pd.read_csv(file_path, delimiter=',')
            # Use the standardize method if available
            if hasattr(DataLoader, '_standardize_txt_columns'):
                df = DataLoader._standardize_txt_columns(DataLoader, df)
            return df
        elif filetype == 'parquet':
            return pd.read_parquet(file_path)
        elif filetype == 'feather':
            return pd.read_feather(file_path)
        elif filetype == 'duckdb':
            conn = duckdb.connect(file_path)
            tables = conn.execute("SHOW TABLES").fetchall()
            if not tables:
                conn.close()
                raise ValueError("No tables found in DuckDB file")
            table_name = tables[0][0]
            df = conn.execute(f"SELECT * FROM {table_name} LIMIT 100").fetchdf()
            conn.close()
            return df
        elif filetype == 'keras':
            return tf.keras.models.load_model(file_path)
        else:
            raise ValueError(f"Unsupported file type: {filetype}")

    @staticmethod
    def save_file_by_type(df, file_path, filetype):
        import duckdb
        import numpy as np
        import tensorflow as tf
        import polars as pl
        if filetype == 'csv':
            df.to_csv(file_path, index=False)
        elif filetype == 'txt':
            df.to_csv(file_path, sep='\t', index=False)
        elif filetype == 'json':
            df.to_json(file_path, orient='records', lines=True)
        elif filetype == 'feather':
            df.reset_index(drop=True).to_feather(file_path)
        elif filetype == 'parquet':
            df.to_parquet(file_path)
        elif filetype == 'keras':
            from tensorflow.keras import Sequential, Input
            from tensorflow.keras.layers import Dense
            model = Sequential([
                Input(shape=(len(df.columns),)),
                Dense(32, activation='relu'),
                Dense(1)
            ])
            model.save(file_path)
        elif filetype == 'duckdb':
            conn = duckdb.connect(file_path)
            conn.register('temp_df', df)
            conn.execute("CREATE TABLE IF NOT EXISTS tickers_data AS SELECT * FROM temp_df")
            conn.unregister('temp_df')
            conn.close()
        elif filetype == 'tensorflow':
            np.savez(file_path, data=df.to_numpy())
        elif filetype == 'polars':
            # Save as .parquet using polars
            if not isinstance(df, pl.DataFrame):
                try:
                    df = pl.from_pandas(df)
                except Exception:
                    raise ValueError("Data must be convertible to polars DataFrame for 'polars' save type.")
            df.write_parquet(file_path)
        elif filetype == 'pyarrow':
            import pyarrow as pa
            import pyarrow.parquet as pq
            table = pa.Table.from_pandas(df)
            pq.write_table(table, file_path)
        else:
            raise ValueError(f"Unsupported save file type: {filetype}")

    def analyze_ticker_distribution(self, data: pd.DataFrame) -> dict:
        """
        Analyze the distribution of records across tickers.
        """
        stats = {
            'total_records': len(data),
            'total_tickers': data['ticker'].nunique(),
            'records_per_ticker': data.groupby('ticker').size().to_dict(),
            'date_ranges': data.groupby('ticker').agg({
                'timestamp': ['min', 'max']
            }).to_dict()
        }
        stats['avg_records_per_ticker'] = stats['total_records'] // stats['total_tickers']
        return stats

    def filter_data_by_date_range(self, data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Filter the dataframe by date range for all tickers.
        """
        try:
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            mask = (data['timestamp'] >= start_date) & (data['timestamp'] <= end_date)
            filtered_data = data.loc[mask]
            
            if filtered_data.empty:
                logging.warning(f"No data found between {start_date} and {end_date}")
            else:
                logging.info(f"Filtered data from {start_date} to {end_date}. Tickers: {filtered_data['ticker'].unique()}")
                
            return filtered_data
        except Exception as e:
            logging.error(f"Error filtering data by date range: {str(e)}")
            raise

    def balance_ticker_data(self, data: pd.DataFrame, target_records_per_ticker: int = None, 
                           min_records_per_ticker: int = None) -> pd.DataFrame:
        """
        Balance data across tickers by sampling or limiting records.
        """
        try:
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            ticker_counts = data.groupby('ticker').size()
            
            if target_records_per_ticker is None:
                target_records_per_ticker = int(ticker_counts.median())
            
            if min_records_per_ticker is None:
                min_records_per_ticker = target_records_per_ticker // 2
                
            balanced_dfs = []
            
            for ticker in ticker_counts.index:
                ticker_data = data[data['ticker'] == ticker]
                
                if len(ticker_data) < min_records_per_ticker:
                    logging.warning(f"Skipping ticker {ticker}: insufficient records ({len(ticker_data)} < {min_records_per_ticker})")
                    continue
                    
                if len(ticker_data) > target_records_per_ticker:
                    ticker_data = ticker_data.sort_values('timestamp')
                    step = len(ticker_data) // target_records_per_ticker
                    balanced_dfs.append(ticker_data.iloc[::step].head(target_records_per_ticker))
                else:
                    balanced_dfs.append(ticker_data)
            
            if not balanced_dfs:
                raise ValueError("No tickers met the minimum record requirement")
                
            balanced_data = pd.concat(balanced_dfs, ignore_index=True)
            
            # Log statistics
            original_stats = self.analyze_ticker_distribution(data)
            balanced_stats = self.analyze_ticker_distribution(balanced_data)
            
            logging.info(f"Original data: {original_stats['total_records']} records across {original_stats['total_tickers']} tickers")
            logging.info(f"Balanced data: {balanced_stats['total_records']} records across {balanced_stats['total_tickers']} tickers")
            
            return balanced_data
            
        except Exception as e:
            logging.error(f"Error balancing ticker data: {str(e)}")
            raise

class DatabaseConnector:
    def __init__(self, db_path: str = '/app/redline_data.duckdb'):
        self.db_path = db_path

    def create_connection(self, db_path: str):
        return duckdb.connect(db_path)

    def read_shared_data(self, table: str, format: str) -> Union[pd.DataFrame, pl.DataFrame, pa.Table]:
        try:
            conn = duckdb.connect(self.db_path)
            df = conn.execute(f"SELECT * FROM {table}").fetchdf()
            conn.close()
            if format == 'polars':
                return pl.from_pandas(df)
            elif format == 'pyarrow':
                return pa.Table.from_pandas(df)
            return df
        except Exception as e:
            logging.error(f"Failed to read from {table}: {str(e)}")
            print(f"Failed to read from {table}: {str(e)}")
            raise

    def write_shared_data(self, table: str, data: Union[pd.DataFrame, pl.DataFrame, pa.Table], format: str) -> None:
        try:
            if isinstance(data, pl.DataFrame):
                data = data.to_pandas()
            elif isinstance(data, pa.Table):
                data = data.to_pandas()
            data['format'] = format
            data = DataLoader.clean_and_select_columns(data)
            # Diagnostic: print dtypes and sample values
            print("Column dtypes before saving:")
            print(data.dtypes)
            for col in ['open', 'high', 'low', 'close', 'vol', 'openint']:
                if col in data.columns:
                    print(f"Sample values for {col}:")
                    print(data[col].head(10).to_list())
            conn = duckdb.connect(self.db_path)
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table} (
                ticker VARCHAR,
                timestamp TIMESTAMP,  # Changed from VARCHAR to TIMESTAMP
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                vol DOUBLE,
                openint DOUBLE,
                format VARCHAR
            )
            """
            conn.execute(create_table_sql)
            # Insert data
            conn.register('temp_df', data)
            insert_sql = f"INSERT INTO {table} SELECT * FROM temp_df"
            conn.execute(insert_sql)
            conn.unregister('temp_df')
            conn.close()
            logging.info(f"Wrote data to {table} in format {format}")
        except Exception as e:
            logging.exception(f"Failed to write to {table}: {str(e)}")
            print(f"Failed to write to {table}: {str(e)}")
            raise

class DataAdapter:
    def prepare_training_data(self, data: Union[List[pd.DataFrame], List[pl.DataFrame], List[pa.Table]], format: str) -> Union[List['np.ndarray'], tf.data.Dataset]:
        try:
            if isinstance(data, list) and data:
                if format == 'numpy':
                    return [d.to_numpy() for d in data if isinstance(d, (pd.DataFrame, pl.DataFrame))]
                elif format == 'tensorflow':
                    return tf.data.Dataset.from_tensor_slices([d.to_numpy() for d in data if isinstance(d, (pd.DataFrame, pl.DataFrame))])
            return []
        except Exception as e:
            logging.error(f"Failed to prepare training data: {str(e)}")
            raise

    def prepare_rl_state(self, data: Union[pd.DataFrame, pl.DataFrame, pa.Table], portfolio: Dict, format: str) -> Union['np.ndarray', tf.Tensor]:
        try:
            if isinstance(data, (pl.DataFrame, pa.Table)):
                data = data.to_pandas()
            state = data[['close']].to_numpy()
            if format == 'tensorflow':
                return tf.convert_to_tensor(state, dtype=tf.float32)
            return state
        except Exception as e:
            logging.error(f"Failed to prepare RL state: {str(e)}")
            raise

    def summarize_preprocessed(self, data: Union[List['np.ndarray'], tf.data.Dataset], format: str) -> Dict:
        try:
            return {'format': format, 'size': len(data)}
        except Exception as e:
            logging.error(f"Failed to summarize preprocessed data: {str(e)}")
            raise

class VirtualScrollingTreeview:
    """A virtual scrolling TreeView that only loads visible items into memory"""
    
    def __init__(self, parent, columns, **kwargs):
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
        """Load only the visible items into the tree"""
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
    
    def __init__(self):
        self.operators = {
            'equals': '=',
            'not_equals': '!=',
            'contains': 'LIKE',
            'not_contains': 'NOT LIKE',
            'greater_than': '>',
            'less_than': '<',
            'greater_equal': '>=',
            'less_equal': '<=',
            'between': 'BETWEEN',
            'in': 'IN',
            'not_in': 'NOT IN',
            'is_null': 'IS NULL',
            'is_not_null': 'IS NOT NULL'
        }
        
        self.date_operators = {
            'equals': '=',
            'not_equals': '!=',
            'greater_than': '>',
            'less_than': '<',
            'greater_equal': '>=',
            'less_equal': '<=',
            'between': 'BETWEEN',
            'in_range': 'BETWEEN'
        }
        
    def build_query(self, conditions, table_name='tickers_data'):
        """Build SQL query from conditions"""
        if not conditions:
            return f"SELECT * FROM {table_name}", []
            
        where_clauses = []
        params = []
        
        for condition in conditions:
            column = condition['column']
            operator = condition['operator']
            value = condition['value']
            
            if operator in ['is_null', 'is_not_null']:
                where_clauses.append(f"{column} {self.operators[operator]}")
            elif operator == 'between':
                where_clauses.append(f"{column} BETWEEN ? AND ?")
                params.extend([value[0], value[1]])
            elif operator == 'in':
                placeholders = ','.join(['?' for _ in value])
                where_clauses.append(f"{column} IN ({placeholders})")
                params.extend(value)
            elif operator in ['contains', 'not_contains']:
                where_clauses.append(f"{column} {self.operators[operator]} ?")
                params.append(f"%{value}%")
            else:
                where_clauses.append(f"{column} {self.operators[operator]} ?")
                params.append(value)
                
        query = f"SELECT * FROM {table_name} WHERE {' AND '.join(where_clauses)}"
        return query, params


class DataSource:
    """Abstract data source for virtual scrolling"""
    
    def __init__(self, file_path, format_type):
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
        
    def get_row(self, index):
        """Get a specific row by index"""
        if self.format_type == 'duckdb':
            query = f"SELECT * FROM tickers_data LIMIT 1 OFFSET {index}"
            result = self.connection.execute(query).fetchone()
            return list(result) if result else []
        else:
            if index < len(self.data):
                return list(self.data.iloc[index])
            return []
            
    def get_rows(self, start, end):
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


class LazyFileLoader:
    """Lazy file loader that processes files in batches to avoid memory issues"""
    
    def __init__(self, file_paths, batch_size=100):
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
        """Process one batch of files and append to DuckDB"""
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
        
        # Combine batch dataframes
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
        """Process all batches sequentially"""
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


class StockAnalyzerGUI:
    def __init__(self, root: tk.Tk, loader: DataLoader, connector: DatabaseConnector):
        self.root = root
        self.loader = loader
        self.connector = connector
        
        # Configure root window
        self.root.title("REDLINE Data Analyzer")
        self.root.geometry("1200x800")
        
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Initialize variables
        self.current_page = 1
        self.rows_per_page = 100
        self.total_pages = 1
        self.scrollbars = {}  # Dictionary to keep track of scrollbars
        self.current_file_path = None
        
        # Store references to data view scrollbars for reuse
        self.data_view_xscroll = None
        self.data_view_yscroll = None
        
        # Thread safety
        self.ui_lock = threading.Lock()
        
        # Create main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky='nsew')
        
        # Setup tabs
        self.setup_tabs()
        
        # Setup event bindings
        self.setup_bindings()
        
        # Setup keyboard shortcuts
        self.setup_keyboard_shortcuts()
        
        # Setup performance monitoring
        self.setup_performance_monitoring()

    def cleanup_scrollbars(self, frame_name):
        """Clean up scrollbars for a given frame"""
        if frame_name in self.scrollbars:
            for scrollbar in self.scrollbars[frame_name]:
                try:
                    if scrollbar.winfo_exists():
                        scrollbar.destroy()
                except:
                    pass  # Ignore errors if widget is already destroyed
            del self.scrollbars[frame_name]

    def safe_update_widget(self, widget_name, update_func):
        """Safely update a widget from background thread"""
        if hasattr(self, widget_name):
            widget = getattr(self, widget_name)
            if widget and widget.winfo_exists():
                def safe_update():
                    with self.ui_lock:
                        update_func()
                self.run_in_main_thread(safe_update)
            else:
                logging.warning(f"Widget {widget_name} does not exist or has been destroyed")
        else:
            logging.warning(f"Widget {widget_name} not found")

    def safe_update_treeview(self, update_func):
        """Safely update the data treeview from background thread"""
        if hasattr(self, 'data_tree') and self.data_tree.winfo_exists():
            def safe_update():
                with self.ui_lock:
                    update_func()
            self.run_in_main_thread(safe_update)
        else:
            logging.warning("Data treeview does not exist or has been destroyed")

    def safe_update_listbox(self, listbox_name, update_func):
        """Safely update a listbox from background thread"""
        if hasattr(self, listbox_name):
            listbox = getattr(self, listbox_name)
            if listbox and listbox.winfo_exists():
                def safe_update():
                    with self.ui_lock:
                        update_func()
                self.run_in_main_thread(safe_update)
            else:
                logging.warning(f"Listbox {listbox_name} does not exist or has been destroyed")
        else:
            logging.warning(f"Listbox {listbox_name} not found")

    def create_scrolled_frame(self, parent, frame_name):
        """Create a frame with scrollbars"""
        frame = ttk.Frame(parent)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Clean up any existing scrollbars
        self.cleanup_scrollbars(frame_name)
        
        # Create scrollbars
        xscroll = ttk.Scrollbar(frame, orient='horizontal')
        yscroll = ttk.Scrollbar(frame, orient='vertical')
        
        # Store scrollbars for cleanup
        self.scrollbars[frame_name] = [xscroll, yscroll]
        
        return frame, xscroll, yscroll

    def setup_tabs(self):
        # Data Loader Tab
        loader_frame = ttk.Frame(self.notebook)
        self.notebook.add(loader_frame, text='Data Loader')

        # Left side: File selection and controls
        left_side_frame = ttk.Frame(loader_frame)
        left_side_frame.grid(row=0, column=0, rowspan=3, padx=10, pady=10, sticky='nsew')

        # File selection group with buttons
        file_group = ttk.LabelFrame(left_side_frame, text="Select Input Files")
        file_group.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Add button frame above listbox
        button_frame = ttk.Frame(file_group)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        # Browse and Select All buttons side by side
        ttk.Button(button_frame, text="Browse Files", command=self.browse_files).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Select All", command=self.select_all_files).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Deselect All", command=self.deselect_all_files).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Analyze Selected", command=self.analyze_selected_files).pack(side='left', padx=5)
        
        # Create a frame for the listbox and its scrollbars
        listbox_frame = ttk.Frame(file_group)
        listbox_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Increased listbox size
        self.input_listbox = tk.Listbox(listbox_frame, selectmode='multiple', width=50, height=15)
        
        # Add scrollbars to listbox
        listbox_scroll_y = ttk.Scrollbar(listbox_frame, orient='vertical', command=self.input_listbox.yview)
        listbox_scroll_x = ttk.Scrollbar(listbox_frame, orient='horizontal', command=self.input_listbox.xview)
        
        # Configure listbox scrolling
        self.input_listbox.configure(yscrollcommand=listbox_scroll_y.set, xscrollcommand=listbox_scroll_x.set)
        
        # Grid layout for listbox and scrollbars
        self.input_listbox.grid(row=0, column=0, sticky='nsew')
        listbox_scroll_y.grid(row=0, column=1, sticky='ns')
        listbox_scroll_x.grid(row=1, column=0, sticky='ew')
        
        # Configure grid weights for listbox frame
        listbox_frame.grid_rowconfigure(0, weight=1)
        listbox_frame.grid_columnconfigure(0, weight=1)

        # Store scrollbars for cleanup
        self.scrollbars['input_listbox'] = [listbox_scroll_x, listbox_scroll_y]

        # Add selection info label
        self.selection_info = ttk.Label(file_group, text="Selected: 0 files")
        self.selection_info.pack(fill='x', padx=5, pady=5)

        # Right side: Controls frame
        right_side_frame = ttk.Frame(loader_frame)
        right_side_frame.grid(row=0, column=1, rowspan=3, padx=10, pady=10, sticky='nsew')

        # Format selection group
        format_group = ttk.LabelFrame(right_side_frame, text="Format Selection")
        format_group.pack(fill='x', padx=5, pady=5)
        
        # Input format
        input_format_frame = ttk.Frame(format_group)
        input_format_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(input_format_frame, text="Input Format:").pack(side='left')
        self.input_format = ttk.Combobox(input_format_frame, 
                                        values=['csv', 'txt', 'json', 'duckdb', 'pyarrow', 'polars', 'keras', 'feather'],
                                        width=30)
        self.input_format.pack(side='right', fill='x', expand=True, padx=5)
        
        # Output format
        output_format_frame = ttk.Frame(format_group)
        output_format_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(output_format_frame, text="Output Format:").pack(side='left')
        self.output_format = ttk.Combobox(output_format_frame,
                                         values=['csv', 'txt', 'json', 'duckdb', 'pyarrow', 'polars', 'keras', 'feather'],
                                         width=30)
        self.output_format.pack(side='right', fill='x', expand=True, padx=5)

        # Date range selection group
        date_frame = ttk.LabelFrame(right_side_frame, text="Date Range Selection")
        date_frame.pack(fill='x', padx=5, pady=5)
        
        # Start date with calendar picker
        start_date_frame = ttk.Frame(date_frame)
        start_date_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(start_date_frame, text="Start Date (YYYY-MM-DD):").pack(side='left')
        self.start_date_entry = ttk.Entry(start_date_frame, width=30)
        self.start_date_entry.pack(side='right', fill='x', expand=True, padx=5)
        
        # End date with calendar picker
        end_date_frame = ttk.Frame(date_frame)
        end_date_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(end_date_frame, text="End Date (YYYY-MM-DD):").pack(side='left')
        self.end_date_entry = ttk.Entry(end_date_frame, width=30)
        self.end_date_entry.pack(side='right', fill='x', expand=True, padx=5)

        # Data balancing options group
        balance_frame = ttk.LabelFrame(right_side_frame, text="Data Balancing Options")
        balance_frame.pack(fill='x', padx=5, pady=5)
        
        # Target records
        target_frame = ttk.Frame(balance_frame)
        target_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(target_frame, text="Target Records per Ticker:").pack(side='left')
        self.target_records_entry = ttk.Entry(target_frame, width=30)
        self.target_records_entry.pack(side='right', fill='x', expand=True, padx=5)
        
        # Minimum records
        min_frame = ttk.Frame(balance_frame)
        min_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(min_frame, text="Minimum Records Required:").pack(side='left')
        self.min_records_entry = ttk.Entry(min_frame, width=30)
        self.min_records_entry.pack(side='right', fill='x', expand=True, padx=5)
        
        # Help text
        help_text = "Leave blank to use automatic values:\n" \
                    "- Target: Median of available records\n" \
                    "- Minimum: Half of target"
        help_label = ttk.Label(balance_frame, text=help_text, wraplength=400)
        help_label.pack(padx=5, pady=5)

        # Action buttons frame
        action_frame = ttk.Frame(right_side_frame)
        action_frame.pack(fill='x', padx=5, pady=10)
        
        # Add buttons with increased size
        ttk.Button(action_frame, text="Preview File", 
                   command=self.preview_selected_loader_file).pack(side='left', padx=5)
        ttk.Button(action_frame, text="Preprocess File", 
                   command=self.preprocess_selected_loader_file).pack(side='left', padx=5)
        ttk.Button(action_frame, text="Merge/Consolidate Files", 
                   command=self.load_and_convert).pack(side='left', padx=5)
        ttk.Button(action_frame, text="?", width=3, 
                   command=self.show_loader_manual).pack(side='left', padx=5)
        ttk.Button(action_frame, text="User Manual", 
                   command=lambda: show_user_manual_popup(self.root)).pack(side='left', padx=5)

        # Progress bar with increased size
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(right_side_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.pack(fill='x', padx=5, pady=10)
        self.progress_bar.pack_forget()  # Hide initially

        # Data View Tab
        view_frame = ttk.Frame(self.notebook)
        self.notebook.add(view_frame, text='Data View')

        # Create horizontal paned window for split view
        paned = ttk.PanedWindow(view_frame, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left side: File browser and database list
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        # Database browser frame
        browser_frame = ttk.LabelFrame(left_frame, text="Database Browser")
        browser_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # File listbox with scrollbars
        list_frame = ttk.Frame(browser_frame)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Configure grid weights for list frame
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame, selectmode='extended')
        file_xscroll = ttk.Scrollbar(list_frame, orient='horizontal', command=self.file_listbox.xview)
        file_yscroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_listbox.yview)
        self.file_listbox.configure(xscrollcommand=file_xscroll.set, yscrollcommand=file_yscroll.set)
        self.file_listbox.grid(row=0, column=0, sticky='nsew')
        file_xscroll.grid(row=1, column=0, sticky='ew')
        file_yscroll.grid(row=0, column=1, sticky='ns')
        self.scrollbars['file_listbox'] = [file_xscroll, file_yscroll]

        # Button frame
        btn_frame = ttk.Frame(browser_frame)
        btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(btn_frame, text="View Selected", command=self.view_selected_file).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_file_list).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Remove", command=self.remove_selected_file).pack(side='left', padx=2)

        # Status indicator label below file_listbox
        self.file_status_label = ttk.Label(browser_frame, text="No file selected", foreground="gray")
        self.file_status_label.pack(fill='x', padx=5, pady=(0, 5))

        # Quick actions frame below status label
        quick_actions_frame = ttk.Frame(browser_frame)
        quick_actions_frame.pack(fill='x', padx=5, pady=(0, 5))
        ttk.Button(quick_actions_frame, text="View", command=self.view_selected_file).pack(side='left', padx=2)
        ttk.Button(quick_actions_frame, text="Export", command=lambda: self.export_data(current_page_only=True)).pack(side='left', padx=2)
        ttk.Button(quick_actions_frame, text="Delete", command=self.remove_selected_file).pack(side='left', padx=2)
        ttk.Button(quick_actions_frame, text="Show Stats", command=self.show_view_statistics).pack(side='left', padx=2)
        
        # Add performance and advanced filtering buttons
        ttk.Button(quick_actions_frame, text="Advanced Filters", 
                  command=self.setup_advanced_filters).pack(side='left', padx=2)
        ttk.Button(quick_actions_frame, text="Virtual Scroll", 
                  command=self.enable_virtual_scrolling).pack(side='left', padx=2)
        ttk.Button(quick_actions_frame, text="Optimize Memory", 
                  command=self.optimize_memory_usage).pack(side='left', padx=2)

        # Bind selection event to update status label
        self.file_listbox.bind('<<ListboxSelect>>', self.update_file_status_label)

        # Right side: Data viewer
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        # Data viewer frame
        viewer_frame = ttk.LabelFrame(right_frame, text="Data Viewer")
        viewer_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Add ticker navigation at the top of viewer frame
        ticker_nav_frame = ttk.Frame(viewer_frame)
        ticker_nav_frame.pack(fill='x', padx=5, pady=5)

        # Ticker selection
        ttk.Label(ticker_nav_frame, text="Current Ticker:").pack(side='left', padx=5)
        self.ticker_var = tk.StringVar()
        self.ticker_combo = ttk.Combobox(ticker_nav_frame, textvariable=self.ticker_var, width=15)
        self.ticker_combo.pack(side='left', padx=5)
        self.ticker_combo.bind('<<ComboboxSelected>>', self.on_ticker_selected)

        # Ticker navigation buttons
        ttk.Button(ticker_nav_frame, text="Previous Ticker", 
                  command=self.previous_ticker).pack(side='left', padx=5)
        ttk.Button(ticker_nav_frame, text="Next Ticker", 
                  command=self.next_ticker).pack(side='left', padx=5)

        # Search frame
        search_frame = ttk.Frame(viewer_frame)
        search_frame.pack(fill='x', padx=5, pady=5)
        
        # Global search
        ttk.Label(search_frame, text="🔍 Search:").pack(side='left', padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<KeyRelease>', self.on_search_change)
        
        # Search options
        self.search_case_sensitive = tk.BooleanVar()
        ttk.Checkbutton(search_frame, text="Case Sensitive", 
                       variable=self.search_case_sensitive).pack(side='left', padx=5)
        
        # Clear search button
        ttk.Button(search_frame, text="Clear", 
                  command=self.clear_search).pack(side='left', padx=5)
        
        # Search results label
        self.search_results_label = ttk.Label(search_frame, text="")
        self.search_results_label.pack(side='right', padx=5)

        # Tree view frame with proper grid configuration
        tree_frame = ttk.Frame(viewer_frame)
        tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Configure grid weights for tree frame
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Create Treeview
        self.data_tree = ttk.Treeview(tree_frame)
        
        # Create and configure scrollbars once - store as instance variables for reuse
        self.data_view_xscroll = ttk.Scrollbar(tree_frame, orient='horizontal', command=self.data_tree.xview)
        self.data_view_yscroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.data_tree.yview)
        self.data_tree.configure(xscrollcommand=self.data_view_xscroll.set, yscrollcommand=self.data_view_yscroll.set)

        # Grid layout for treeview and scrollbars
        self.data_tree.grid(row=0, column=0, sticky='nsew')
        self.data_view_xscroll.grid(row=1, column=0, sticky='ew')
        self.data_view_yscroll.grid(row=0, column=1, sticky='ns')

        # Store scrollbars for cleanup (but don't recreate them)
        self.scrollbars['data_view'] = [self.data_view_xscroll, self.data_view_yscroll]

        # Control panel frame
        control_frame = ttk.Frame(viewer_frame)
        control_frame.pack(fill='x', padx=5, pady=5)

        # Left side controls
        left_controls = ttk.Frame(control_frame)
        left_controls.pack(side='left', fill='x', expand=True)

        # Page size controls
        page_size_frame = ttk.Frame(left_controls)
        page_size_frame.pack(side='left', padx=5)
        ttk.Label(page_size_frame, text="Rows per page:").pack(side='left')
        
        # Initialize pagination variables
        self.current_page = 1
        self.rows_per_page = 100
        self.total_pages = 1

        # Predefined page sizes
        self.page_size_var = tk.StringVar(value=str(self.rows_per_page))
        page_size_combo = ttk.Combobox(page_size_frame, textvariable=self.page_size_var,
                                     values=['50', '100', '200', '500', '1000'], width=5)
        page_size_combo.pack(side='left', padx=2)

        # Custom page size
        self.custom_page_size = ttk.Entry(page_size_frame, width=6)
        self.custom_page_size.pack(side='left', padx=2)
        ttk.Button(page_size_frame, text="Set", 
                  command=self.apply_custom_page_size).pack(side='left', padx=2)

        # Navigation controls
        nav_frame = ttk.Frame(left_controls)
        nav_frame.pack(side='left', padx=10)

        ttk.Button(nav_frame, text="<<", command=lambda: self.change_page(1)).pack(side='left', padx=2)
        ttk.Button(nav_frame, text="<", 
                  command=lambda: self.change_page(max(1, self.current_page - 1))).pack(side='left', padx=2)

        # Jump to page
        self.jump_page_var = tk.StringVar()
        jump_entry = ttk.Entry(nav_frame, textvariable=self.jump_page_var, width=6)
        jump_entry.pack(side='left', padx=2)
        ttk.Button(nav_frame, text="Go", command=self.jump_to_page).pack(side='left', padx=2)

        self.page_label = ttk.Label(nav_frame, text="Page 1 of 1")
        self.page_label.pack(side='left', padx=10)

        ttk.Button(nav_frame, text=">",
                  command=lambda: self.change_page(self.current_page + 1)).pack(side='left', padx=2)
        ttk.Button(nav_frame, text=">>",
                  command=lambda: self.change_page(self.total_pages)).pack(side='left', padx=2)

        # Right side controls
        right_controls = ttk.Frame(control_frame)
        right_controls.pack(side='right')

        # Export controls
        export_frame = ttk.Frame(right_controls)
        export_frame.pack(side='left', padx=5)
        ttk.Button(export_frame, text="Export Current", 
                  command=lambda: self.export_data(current_page_only=True)).pack(side='left', padx=2)
        ttk.Button(export_frame, text="Export All", 
                  command=lambda: self.export_data(current_page_only=False)).pack(side='left', padx=2)

        # Refresh file list
        self.refresh_file_list()

    def browse_files(self):
        filetypes = [(desc, pattern) for (_, desc, pattern) in DataLoader.FORMAT_DIALOG_INFO.values()]
        files = filedialog.askopenfilenames(filetypes=filetypes)
        self.input_listbox.delete(0, tk.END)
        detected_types = []
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            fmt = DataLoader.EXT_TO_FORMAT.get(ext, 'unknown')
            detected_types.append(fmt)
            display_name = f"{file} [{fmt}]"
            self.input_listbox.insert(tk.END, display_name)
        
        # Set input format to the most common detected type
        if detected_types:
            from collections import Counter
            most_common = Counter(detected_types).most_common(1)[0][0]
            if most_common != 'unknown':
                self.input_format.set(most_common)
        
        # Update selection info
        self.update_selection_info()

    def select_all_files(self):
        """Select all files in the listbox"""
        self.input_listbox.select_set(0, tk.END)
        self.update_selection_info()

    def deselect_all_files(self):
        """Deselect all files in the listbox"""
        self.input_listbox.selection_clear(0, tk.END)
        self.update_selection_info()

    def update_selection_info(self):
        """Update the selection info label"""
        selected_count = len(self.input_listbox.curselection())
        self.selection_info.config(text=f"Selected: {selected_count} files")

    def analyze_selected_files(self):
        """Analyze currently selected files"""
        selections = self.input_listbox.curselection()
        if not selections:
            messagebox.showerror("Error", "No files selected")
            return
        
        # Get selected file paths
        file_paths = [self.input_listbox.get(idx).split(' [')[0] for idx in selections]
        
        def worker():
            try:
                self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack())
                self.run_in_main_thread(lambda *a, **k: self.progress_var.set(10))
                
                # Analyze files
                analysis = self.analyze_stooq_files(file_paths)
                
                # Update GUI with analysis
                def update_gui():
                    self.show_stooq_analysis_popup(analysis)
                    
                    # Auto-fill date range if found
                    if analysis['summary']['earliest_date'] and analysis['summary']['latest_date']:
                        self.start_date_entry.delete(0, tk.END)
                        self.start_date_entry.insert(0, 
                            analysis['summary']['earliest_date'].strftime('%Y-%m-%d'))
                        self.end_date_entry.delete(0, tk.END)
                        self.end_date_entry.insert(0, 
                            analysis['summary']['latest_date'].strftime('%Y-%m-%d'))
                    
                    # Calculate and set suggested record counts
                    if analysis['summary']['total_records'] and analysis['summary']['total_tickers']:
                        avg_records = analysis['summary']['total_records'] // analysis['summary']['total_tickers']
                        self.target_records_entry.delete(0, tk.END)
                        self.target_records_entry.insert(0, str(avg_records))
                        self.min_records_entry.delete(0, tk.END)
                        self.min_records_entry.insert(0, str(avg_records // 2))
                
                self.run_in_main_thread(lambda *a, **k: update_gui())
                
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Analysis failed: {error_msg}")
                def show_error():
                    messagebox.showerror("Error", f"Analysis failed: {error_msg}")
                self.run_in_main_thread(lambda *a, **k: show_error())
            finally:
                def hide_progress():
                    self.progress_bar.pack_forget()
                self.run_in_main_thread(lambda *a, **k: hide_progress())
        
        threading.Thread(target=worker, daemon=True).start()

    def load_and_convert(self):
        def worker():
            try:
                input_format = self.input_format.get()
                output_format = self.output_format.get()
                
                # Get selected files
                selections = self.input_listbox.curselection()
                if not selections:
                    self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", "No files selected"))
                    return
                
                # Get file paths
                file_paths = [self.input_listbox.get(idx).split(' [')[0] for idx in selections]
                
                self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack())
                self.run_in_main_thread(lambda *a, **k: self.progress_var.set(10))
                
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
                        self.run_in_main_thread(lambda: self.progress_var.set(total_progress))
                    
                    # Create lazy loader
                    lazy_loader = LazyFileLoader(file_paths, batch_size=100)
                    
                    # Process all batches
                    total_processed = lazy_loader.process_all_batches(
                        temp_db_path, 
                        input_format, 
                        lazy_progress_callback
                    )
                    
                    if total_processed == 0:
                        self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", "No valid data loaded"))
                        self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack_forget())
                        return
                    
                    # Load the processed data from DuckDB for further processing
                    conn = duckdb.connect(temp_db_path)
                    data = conn.execute("SELECT * FROM tickers_data").fetchdf()
                    conn.close()
                    
                    # Clean up temporary file
                    if os.path.exists(temp_db_path):
                        os.remove(temp_db_path)
                        
                    print(f"Lazy loading completed: {total_processed} files processed")
                    
                else:
                    # Use original method for small datasets
                    dfs = []
                    for idx, file_path in enumerate(file_paths):
                        try:
                            # Read the raw data
                            df = pd.read_csv(file_path)
                            
                            # If input format is txt (Stooq), standardize the columns
                            if input_format.lower() == 'txt':
                                df = self.loader._standardize_txt_columns(df)
                            
                            if df is not None and not df.empty:
                                dfs.append(df)
                            
                            progress = 30 + (40 * (idx + 1) / len(file_paths))
                            self.run_in_main_thread(lambda *a, **k: self.progress_var.set(progress))
                            
                        except Exception as error:
                            logging.error(f"Error processing file {file_path}: {str(error)}")
                            print(f"DEBUG: file_path={file_path} (type={type(file_path)})")
                            if not isinstance(file_path, str):
                                file_path_str = str(file_path)
                            else:
                                file_path_str = file_path
                            self.run_in_main_thread(
                                lambda error=error, file_path_str=file_path_str, *a, **k: (
                                    messagebox.showerror(
                                        "Error",
                                        f"Failed to process {os.path.basename(str(file_path_str)) if isinstance(file_path_str, (str, bytes, os.PathLike)) else file_path_str}: {str(error)}"
                                    )
                                ))
                            continue
                    
                    if not dfs:
                        self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", "No valid data loaded"))
                        self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack_forget())
                        return
                    
                    # Combine all dataframes
                    data = pd.concat(dfs, ignore_index=True)
                
                # Apply date filtering if specified
                start_date = self.start_date_entry.get()
                end_date = self.end_date_entry.get()
                
                if start_date and end_date:
                    try:
                        data = self.loader.filter_data_by_date_range(data, start_date, end_date)
                    except Exception as error:
                        self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", f"Date filtering failed: {str(error)}"))
                        self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack_forget())
                        return
                
                self.run_in_main_thread(lambda *a, **k: self.progress_var.set(80))
                
                # Balance the data if parameters are provided
                try:
                    target_records = int(self.target_records_entry.get()) if self.target_records_entry.get() else None
                    min_records = int(self.min_records_entry.get()) if self.min_records_entry.get() else None
                    
                    if target_records or min_records:
                        data = self.loader.balance_ticker_data(data, target_records, min_records)
                except Exception as error:
                    self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", f"Data balancing failed: {str(error)}"))
                    self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack_forget())
                    return
                
                self.run_in_main_thread(lambda *a, **k: self.progress_var.set(90))
                
                # Handle duplicates and save
                dropped_dupes = len(data) - len(data.drop_duplicates())
                data = data.drop_duplicates()
                
                # Call data cleaning and save in main thread
                self.run_in_main_thread(lambda *a, **k: self.data_cleaning_and_save(data, input_format, output_format, dropped_dupes))
                
            except Exception as error:
                logging.error(f"Data processing failed: {str(error)}")
                self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", f"Processing failed: {str(error)}"))
            finally:
                self.run_in_main_thread(lambda *a, **k: self.progress_bar.pack_forget())
        
        threading.Thread(target=worker, daemon=True).start()

    def data_cleaning_and_save(self, data, input_format, output_format, dropped_dupes):
        # This runs in the main thread
        dropna = messagebox.askyesno("Data Cleaning", f"{dropped_dupes} duplicate rows removed.\nDo you want to drop rows with missing values?")
        if dropna:
            before_dropna = len(data)
            data = data.dropna()
            after_dropna = len(data)
            dropped_na = before_dropna - after_dropna
            messagebox.showinfo("Data Cleaning", f"{dropped_na} rows with missing values dropped.")
        # Save as a single output file
        from tkinter import filedialog
        base_name = "merged_data"
        dialog_info = DataLoader.FORMAT_DIALOG_INFO.get(output_format, ('.dat', 'All Files', '*.*'))
        out_ext, desc, pattern = dialog_info
        save_path = filedialog.asksaveasfilename(
            defaultextension=out_ext,
            filetypes=[(desc, pattern)],
            initialdir='data',
            initialfile=base_name + out_ext
        )
        if not save_path:
            self.progress_bar.pack_forget()
            return
        # Always overwrite the file (no append)
        converted = self.loader.convert_format(data, input_format, output_format)
        DataLoader.save_file_by_type(converted, save_path, output_format)
        self.refresh_file_list()
        self.progress_bar.pack_forget()
        print("Success: Files merged/consolidated, cleaned, and saved as one file")
        messagebox.showinfo("Success", "Files merged/consolidated, cleaned, and saved as one file")

        # Automatically select and preview the new file in Data View
        for idx in range(self.file_listbox.size()):
            entry = self.file_listbox.get(idx)
            if save_path in entry:
                self.file_listbox.selection_clear(0, tk.END)
                self.file_listbox.selection_set(idx)
                self.file_listbox.see(idx)
                self.view_selected_file()
                # self.refresh_data()  # REMOVED - could cause race conditions
                break

    def refresh_file_list(self):
        # Store current selections before clearing
        current_selections = []
        for idx in self.file_listbox.curselection():
            current_selections.append(self.file_listbox.get(idx))
        
        # Recursively list all supported files in the data directory and subdirectories
        self.file_listbox.delete(0, tk.END)
        data_dir = 'data'  # preferred data directory
        supported_exts = tuple(DataLoader.EXT_TO_FORMAT.keys())
        for root, _, files in os.walk(data_dir):
            for fname in files:
                if fname.endswith(supported_exts):
                    fpath = os.path.join(root, fname)
                    ext = os.path.splitext(fname)[1].lower()
                    fmt = DataLoader.EXT_TO_FORMAT.get(ext, 'unknown')
                    display_name = f"{fpath} [{fmt}]"
                    self.file_listbox.insert(tk.END, display_name)
        
        # Restore selections if files still exist
        for selection in current_selections:
            for idx in range(self.file_listbox.size()):
                if self.file_listbox.get(idx) == selection:
                    self.file_listbox.selection_set(idx)
                    break

    def setup_data_view_controls(self, parent_frame):
        """Setup the control panel for data view features"""
        control_frame = ttk.Frame(parent_frame)
        control_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=5, pady=5)

        # Add ticker navigation frame at the top
        ticker_frame = ttk.LabelFrame(control_frame, text="Ticker Navigation")
        ticker_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)

        # Ticker selection
        ttk.Label(ticker_frame, text="Current Ticker:").grid(row=0, column=0, padx=5)
        self.ticker_var = tk.StringVar()
        self.ticker_combo = ttk.Combobox(ticker_frame, textvariable=self.ticker_var, width=15)
        self.ticker_combo.grid(row=0, column=1, padx=5)
        self.ticker_combo.bind('<<ComboboxSelected>>', self.on_ticker_selected)

        # Ticker navigation buttons
        ttk.Button(ticker_frame, text="Previous Ticker", 
                  command=self.previous_ticker).grid(row=0, column=2, padx=5)
        ttk.Button(ticker_frame, text="Next Ticker", 
                  command=self.next_ticker).grid(row=0, column=3, padx=5)

        # Left side controls
        left_controls = ttk.Frame(control_frame)
        left_controls.grid(row=1, column=0, sticky='w')

        # Page size controls
        page_size_frame = ttk.Frame(left_controls)
        page_size_frame.grid(row=0, column=0, padx=5)
        ttk.Label(page_size_frame, text="Rows per page:").grid(row=0, column=0)

        # Predefined page sizes
        self.page_size_var = tk.StringVar(value=str(self.rows_per_page))
        page_size_combo = ttk.Combobox(page_size_frame, textvariable=self.page_size_var,
                                     values=['50', '100', '200', '500', '1000'], width=5)
        page_size_combo.grid(row=0, column=1, padx=2)

        # Custom page size
        self.custom_page_size = ttk.Entry(page_size_frame, width=6)
        self.custom_page_size.grid(row=0, column=2, padx=2)
        ttk.Button(page_size_frame, text="Set", 
                  command=self.apply_custom_page_size).grid(row=0, column=3, padx=2)

        # Navigation controls
        nav_frame = ttk.Frame(left_controls)
        nav_frame.grid(row=0, column=1, padx=10)

        ttk.Button(nav_frame, text="<<", command=lambda: self.change_page(1)).grid(row=0, column=0, padx=2)
        ttk.Button(nav_frame, text="<", 
                  command=lambda: self.change_page(max(1, self.current_page - 1))).grid(row=0, column=1, padx=2)

        # Jump to page
        self.jump_page_var = tk.StringVar()
        jump_entry = ttk.Entry(nav_frame, textvariable=self.jump_page_var, width=6)
        jump_entry.grid(row=0, column=2, padx=2)
        ttk.Button(nav_frame, text="Go", command=self.jump_to_page).grid(row=0, column=3, padx=2)

        self.page_label = ttk.Label(nav_frame, text="Page 1 of 1")
        self.page_label.grid(row=0, column=4, padx=10)

        ttk.Button(nav_frame, text=">",
                  command=lambda: self.change_page(self.current_page + 1)).grid(row=0, column=5, padx=2)
        ttk.Button(nav_frame, text=">>",
                  command=lambda: self.change_page(self.total_pages)).grid(row=0, column=6, padx=2)

        # Right side controls
        right_controls = ttk.Frame(control_frame)
        right_controls.grid(row=1, column=1, sticky='e')

        # Export controls
        export_frame = ttk.Frame(right_controls)
        export_frame.grid(row=0, column=0, padx=5)
        ttk.Button(export_frame, text="Export Current", 
                  command=lambda: self.export_data(current_page_only=True)).grid(row=0, column=0, padx=2)
        ttk.Button(export_frame, text="Export All", 
                  command=lambda: self.export_data(current_page_only=False)).grid(row=0, column=1, padx=2)

        # Configure grid weights
        control_frame.grid_columnconfigure(1, weight=1)  # Give extra space to right side

        return control_frame

    def change_page(self, new_page):
        """Handle page changes in the data view"""
        if new_page < 1 or new_page > self.total_pages:
            return
            
        self.current_page = new_page
        
        # If we're viewing a specific ticker, load that ticker's data for the new page
        current_ticker = self.ticker_var.get()
        if current_ticker:
            self.load_ticker_data(current_ticker)
        else:
            # Otherwise, load all data for the new page
            self.view_selected_file()

    def load_ticker_list(self):
        """Load list of available tickers from the database"""
        try:
            if hasattr(self, 'current_file_path') and self.current_file_path.endswith('.duckdb'):
                conn = duckdb.connect(self.current_file_path)
                try:
                    tickers = conn.execute("SELECT DISTINCT ticker FROM tickers_data ORDER BY ticker").fetchall()
                    conn.close()
                    
                    # Update ticker combobox
                    ticker_list = [t[0] for t in tickers if t[0]]  # Filter out None/empty tickers
                    
                    # Check if ticker_combo exists and is not destroyed
                    if hasattr(self, 'ticker_combo') and self.ticker_combo.winfo_exists():
                        self.ticker_combo['values'] = ticker_list
                        
                        # Set initial ticker if not already set
                        if not self.ticker_var.get() and ticker_list:
                            self.ticker_var.set(ticker_list[0])
                            self.on_ticker_selected()
                except Exception as e:
                    if conn:
                        conn.close()
                    logging.error(f"Database query failed: {str(e)}")
                    messagebox.showerror("Error", f"Failed to query database: {str(e)}")
        except Exception as e:
            logging.error(f"Failed to load ticker list: {str(e)}")
            messagebox.showerror("Error", f"Failed to load ticker list: {str(e)}")

    def load_ticker_data(self, ticker):
        """Load data for a specific ticker"""
        try:
            if hasattr(self, 'current_file_path') and self.current_file_path.endswith('.duckdb'):
                conn = duckdb.connect(self.current_file_path)
                try:
                    # Get total count for pagination
                    total_count = conn.execute(
                        "SELECT COUNT(*) FROM tickers_data WHERE ticker = ?", 
                        [ticker]
                    ).fetchone()[0]
                    
                    self.total_pages = (total_count + self.rows_per_page - 1) // self.rows_per_page
                    self.current_page = min(self.current_page, self.total_pages)  # Ensure current page is valid
                    
                    # Get data for current page
                    offset = (self.current_page - 1) * self.rows_per_page
                    query = f"""
                    SELECT * FROM tickers_data 
                    WHERE ticker = ?
                    ORDER BY timestamp
                    LIMIT {self.rows_per_page} 
                    OFFSET {offset}
                    """
                    df = conn.execute(query, [ticker]).fetchdf()
                    conn.close()
                    
                    # Don't clean up scrollbars - reuse existing ones
                    # self.cleanup_scrollbars('data_view')  # REMOVED
                    
                    # Only set up columns if changed
                    cols = list(df.columns)
                    if list(self.data_tree['columns']) != cols:
                        self.data_tree['columns'] = cols
                        self.data_tree['show'] = 'headings'
                        for col in cols:
                            self.data_tree.heading(col, text=col)
                            self.data_tree.column(col, width=100)
                    
                    # Hide Treeview during insert
                    self.data_tree.grid_remove()
                    self.data_tree.delete(*self.data_tree.get_children())
                    rows = [tuple(row) for _, row in df.iterrows()]
                    for row in rows:
                        self.data_tree.insert('', 'end', values=row)
                    self.data_tree.grid()
                    
                    # Scrollbars are already created and configured - no need to recreate them
                    # The existing scrollbars will automatically work with the updated treeview
                    
                    # Update page info
                    if hasattr(self, 'page_label'):
                        self.page_label.config(text=f"Page {self.current_page} of {self.total_pages}")
                    
                except Exception as e:
                    if conn:
                        conn.close()
                    logging.error(f"Database query failed: {str(e)}")
                    messagebox.showerror("Error", f"Failed to query database: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Failed to load ticker data: {str(e)}")
            messagebox.showerror("Error", f"Failed to load ticker data: {str(e)}")

    def on_ticker_selected(self, event=None):
        """Handle ticker selection change"""
        selected_ticker = self.ticker_var.get()
        if selected_ticker:
            self.load_ticker_data(selected_ticker)

    def next_ticker(self):
        """Switch to next ticker in the list"""
        current_ticker = self.ticker_var.get()
        values = self.ticker_combo['values']
        if values:
            try:
                current_index = values.index(current_ticker)
                next_index = (current_index + 1) % len(values)
                self.ticker_var.set(values[next_index])
                self.load_ticker_data(values[next_index])
            except ValueError:
                # If current ticker not in list, select first ticker
                self.ticker_var.set(values[0])
                self.load_ticker_data(values[0])

    def previous_ticker(self):
        """Switch to previous ticker in the list"""
        current_ticker = self.ticker_var.get()
        values = self.ticker_combo['values']
        if values:
            try:
                current_index = values.index(current_ticker)
                prev_index = (current_index - 1) % len(values)
                self.ticker_var.set(values[prev_index])
                self.load_ticker_data(values[prev_index])
            except ValueError:
                # If current ticker not in list, select last ticker
                self.ticker_var.set(values[-1])
                self.load_ticker_data(values[-1])

    def setup_smart_columns(self, df):
        """Automatically configure columns for better display based on data types"""
        cols = list(df.columns)
        
        # Set up columns with smart configuration
        self.data_tree['columns'] = cols
        self.data_tree['show'] = 'headings'
        
        for col in cols:
            # Default settings
            col_width = 100
            anchor = 'center'
            
            # Detect column type and set appropriate configuration
            if df[col].dtype in ['int64', 'float64']:
                # Numeric columns - right align, smaller width
                col_width = 80
                anchor = 'e'
            elif 'date' in col.lower() or 'time' in col.lower():
                # Date/time columns - center align, wider width
                col_width = 120
                anchor = 'center'
            elif df[col].dtype == 'object':
                # Text columns - left align, dynamic width
                try:
                    # Calculate width based on content length
                    max_len = df[col].astype(str).str.len().max()
                    col_width = min(max_len * 8, 200)  # Cap at 200px
                except:
                    col_width = 120
                anchor = 'w'
            else:
                # Default for other types
                col_width = 100
                anchor = 'center'
            
            # Set column configuration
            self.data_tree.heading(col, text=col)
            self.data_tree.column(col, width=col_width, anchor=anchor, stretch=True)

    def view_selected_file(self):
        """View the selected file in the data viewer"""
        try:
            selection = self.file_listbox.curselection()
            if not selection:
                messagebox.showerror("Error", "No file selected")
                return
                
            file_path = self.file_listbox.get(selection[0])
            self.current_file_path = file_path.split(' [')[0]
            ext = os.path.splitext(self.current_file_path)[1].lower()
            fmt = DataLoader.EXT_TO_FORMAT.get(ext, None)
            
            # Validate the file before loading
            if not self.validate_data_file(self.current_file_path, fmt):
                return
            
            def worker():
                try:
                    if fmt == 'duckdb':
                        # Load ticker list first
                        def update_tickers():
                            self.load_ticker_list()
                        self.run_in_main_thread(update_tickers)
                        
                        # Load data
                        conn = duckdb.connect(self.current_file_path)
                        total_count = conn.execute("SELECT COUNT(*) FROM tickers_data").fetchone()[0]
                        self.total_pages = (total_count + self.rows_per_page - 1) // self.rows_per_page
                        
                        offset = (self.current_page - 1) * self.rows_per_page
                        query = f"""
                        SELECT * FROM tickers_data 
                        LIMIT {self.rows_per_page} 
                        OFFSET {offset}
                        """
                        df = conn.execute(query).fetchdf()
                        conn.close()
                        
                        def update_view():
                            # Use smart column setup
                            self.setup_smart_columns(df)
                            
                            # Store original data for searching
                            self.store_original_data(df)
                            
                            # Hide Treeview during insert
                            self.data_tree.grid_remove()
                            self.data_tree.delete(*self.data_tree.get_children())
                            rows = [tuple(row) for _, row in df.iterrows()]
                            for row in rows:
                                self.data_tree.insert('', 'end', values=row)
                            self.data_tree.grid()
                            # Update page info
                            if hasattr(self, 'page_label'):
                                self.page_label.config(text=f"Page {self.current_page} of {self.total_pages}")
                        self.run_in_main_thread(update_view)
                    else:
                        # Handle other file types
                        df = DataLoader.load_file_by_type(self.current_file_path, fmt)
                        # Convert Polars or PyArrow to pandas DataFrame if needed
                        import polars as pl
                        import pyarrow as pa
                        if isinstance(df, pl.DataFrame):
                            df = df.to_pandas()
                        elif isinstance(df, pa.Table):
                            df = df.to_pandas()
                        if isinstance(df, pd.DataFrame):
                            # In-memory pagination for file-based data
                            total_count = len(df)
                            self.total_pages = (total_count + self.rows_per_page - 1) // self.rows_per_page
                            self.current_page = min(self.current_page, self.total_pages) if self.total_pages > 0 else 1
                            start = (self.current_page - 1) * self.rows_per_page
                            end = start + self.rows_per_page
                            page_df = df.iloc[start:end]
                            def update_view():
                                # Use smart column setup
                                self.setup_smart_columns(page_df)
                                
                                # Store original data for searching
                                self.store_original_data(page_df)
                                
                                self.data_tree.grid_remove()
                                self.data_tree.delete(*self.data_tree.get_children())
                                rows = [tuple(row) for _, row in page_df.iterrows()]
                                for row in rows:
                                    self.data_tree.insert('', 'end', values=row)
                                self.data_tree.grid()
                                if hasattr(self, 'page_label'):
                                    self.page_label.config(text=f"Page {self.current_page} of {self.total_pages}")
                            self.run_in_main_thread(update_view)
                except Exception as e:
                    logging.error(f"Failed to view file: {str(e)}")
                    self.run_in_main_thread(lambda e=e, *a, **k: self.show_enhanced_error("File Loading Error", f"Failed to view file: {str(e)}", self.current_file_path))
            
            threading.Thread(target=worker, daemon=True).start()
            
        except Exception as e:
            logging.error(f"Error in view_selected_file: {str(e)}")
            self.show_enhanced_error("Error", f"Error viewing file: {str(e)}", self.current_file_path if hasattr(self, 'current_file_path') else None)

    def apply_custom_page_size(self):
        """Apply custom page size from entry"""
        try:
            new_size = int(self.custom_page_size.get())
            if new_size > 0:
                self.rows_per_page = new_size
                self.current_page = 1
                self.view_selected_file()
            else:
                messagebox.showerror("Error", "Page size must be positive")
        except ValueError:
            messagebox.showerror("Error", "Invalid page size")

    def jump_to_page(self):
        """Jump to specific page number"""
        try:
            page = int(self.jump_page_var.get())
            if 1 <= page <= self.total_pages:
                self.change_page(page)
            else:
                messagebox.showerror("Error", f"Page number must be between 1 and {self.total_pages}")
        except ValueError:
            messagebox.showerror("Error", "Invalid page number")

    def setup_column_sorting(self):
        """Setup column sorting for the data tree"""
        for col in self.data_tree['columns']:
            self.data_tree.heading(col, text=col,
                command=lambda c=col: self.sort_tree_column(c))
        
        # Store sort state
        self.sort_col = None
        self.sort_reverse = False

    def sort_tree_column(self, col):
        """Sort tree data when a column header is clicked"""
        items = [(self.data_tree.set(item, col), item) for item in self.data_tree.get_children('')]
        
        # Toggle sort direction if same column
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
        self.sort_col = col
        
        # Try numeric sort first
        try:
            items.sort(key=lambda x: float(x[0]), reverse=self.sort_reverse)
        except ValueError:
            items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)
        
        for index, (_, item) in enumerate(items):
            self.data_tree.move(item, '', index)
        
        # Update header to show sort direction
        for header in self.data_tree['columns']:
            if header == col:
                direction = " ▼" if self.sort_reverse else " ▲"
                self.data_tree.heading(header, text=header + direction)
            else:
                self.data_tree.heading(header, text=header.replace(" ▼", "").replace(" ▲", ""))

    def setup_column_filters(self):
        """Setup column filtering controls"""
        self.filter_frame.destroy()
        self.filter_frame = ttk.Frame(self.data_tree.master)
        self.filter_frame.grid(row=2, column=0, columnspan=2, sticky='ew', padx=5, pady=5)  # Changed from pack to grid
        
        # Store filter entries
        self.filter_entries = {}
        
        # Create filter entries for each column
        for i, col in enumerate(self.data_tree['columns']):
            frame = ttk.Frame(self.filter_frame)
            frame.grid(row=0, column=i, padx=2)  # Changed from pack to grid
            ttk.Label(frame, text=col).grid(row=0, column=0)  # Changed from pack to grid
            entry = ttk.Entry(frame, width=10)
            entry.grid(row=1, column=0)  # Changed from pack to grid
            self.filter_entries[col] = entry
        
        # Add filter buttons
        btn_frame = ttk.Frame(self.filter_frame)
        btn_frame.grid(row=0, column=len(self.data_tree['columns']), padx=5)  # Changed from pack to grid
        
        ttk.Button(btn_frame, text="Apply Filters",
                  command=self.apply_filters).grid(row=0, column=0, padx=2)  # Changed from pack to grid
        ttk.Button(btn_frame, text="Clear Filters",
                  command=self.clear_filters).grid(row=1, column=0, padx=2)  # Changed from pack to grid

        # Configure grid weights
        self.filter_frame.grid_columnconfigure(tuple(range(len(self.data_tree['columns']))), weight=1)

    def setup_advanced_filters(self):
        """Setup advanced filtering with query builder"""
        # Create advanced filter window
        self.advanced_filter_window = tk.Toplevel(self.root)
        self.advanced_filter_window.title("Advanced Query Builder")
        self.advanced_filter_window.geometry("800x600")
        
        # Main frame
        main_frame = ttk.Frame(self.advanced_filter_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Query conditions frame
        conditions_frame = ttk.LabelFrame(main_frame, text="Query Conditions")
        conditions_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # Conditions list
        self.conditions_list = tk.Listbox(conditions_frame, height=10)
        self.conditions_list.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbar for conditions
        conditions_scroll = ttk.Scrollbar(conditions_frame, orient='vertical', command=self.conditions_list.yview)
        conditions_scroll.pack(side='right', fill='y')
        self.conditions_list.configure(yscrollcommand=conditions_scroll.set)
        
        # Condition builder frame
        builder_frame = ttk.LabelFrame(main_frame, text="Add Condition")
        builder_frame.pack(fill='x', pady=(0, 10))
        
        # Column selection
        col_frame = ttk.Frame(builder_frame)
        col_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(col_frame, text="Column:").pack(side='left')
        self.filter_column_var = tk.StringVar()
        self.filter_column_combo = ttk.Combobox(col_frame, textvariable=self.filter_column_var, width=15)
        self.filter_column_combo.pack(side='left', padx=5)
        
        # Operator selection
        op_frame = ttk.Frame(builder_frame)
        op_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(op_frame, text="Operator:").pack(side='left')
        self.filter_operator_var = tk.StringVar()
        self.filter_operator_combo = ttk.Combobox(op_frame, textvariable=self.filter_operator_var, width=15)
        self.filter_operator_combo.pack(side='left', padx=5)
        
        # Value entry
        val_frame = ttk.Frame(builder_frame)
        val_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(val_frame, text="Value:").pack(side='left')
        self.filter_value_entry = ttk.Entry(val_frame, width=20)
        self.filter_value_entry.pack(side='left', padx=5)
        
        # Add condition button
        ttk.Button(builder_frame, text="Add Condition", 
                  command=self.add_filter_condition).pack(pady=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(buttons_frame, text="Apply Query", 
                  command=self.apply_advanced_filters).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Clear All", 
                  command=self.clear_advanced_filters).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Save Query", 
                  command=self.save_query).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Load Query", 
                  command=self.load_query).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Close", 
                  command=self.advanced_filter_window.destroy).pack(side='right', padx=5)
        
        # Initialize query builder
        self.query_builder = AdvancedQueryBuilder()
        self.filter_conditions = []
        
        # Populate column and operator lists
        if hasattr(self, 'data_tree') and self.data_tree['columns']:
            self.filter_column_combo['values'] = list(self.data_tree['columns'])
            if self.data_tree['columns']:
                self.filter_column_combo.set(self.data_tree['columns'][0])
        
        self.filter_operator_combo['values'] = list(self.query_builder.operators.keys())
        if self.query_builder.operators:
            self.filter_operator_combo.set(list(self.query_builder.operators.keys())[0])

    def add_filter_condition(self):
        """Add a new filter condition"""
        column = self.filter_column_var.get()
        operator = self.filter_operator_var.get()
        value = self.filter_value_entry.get()
        
        if not column or not operator:
            messagebox.showerror("Error", "Please select column and operator")
            return
            
        # Handle different value types
        if operator in ['between']:
            # For between operator, expect two values separated by comma
            values = value.split(',')
            if len(values) != 2:
                messagebox.showerror("Error", "Between operator requires two values separated by comma")
                return
            value = [v.strip() for v in values]
        elif operator in ['in']:
            # For in operator, expect comma-separated values
            value = [v.strip() for v in value.split(',')]
        elif operator in ['is_null', 'is_not_null']:
            value = None
        else:
            # Try to convert to appropriate type
            try:
                if 'date' in column.lower() or 'time' in column.lower():
                    # Keep as string for dates
                    pass
                else:
                    # Try numeric conversion
                    value = float(value)
            except ValueError:
                # Keep as string if conversion fails
                pass
        
        condition = {
            'column': column,
            'operator': operator,
            'value': value
        }
        
        self.filter_conditions.append(condition)
        self.update_conditions_display()
        
        # Clear value entry
        self.filter_value_entry.delete(0, tk.END)

    def update_conditions_display(self):
        """Update the conditions list display"""
        self.conditions_list.delete(0, tk.END)
        for i, condition in enumerate(self.filter_conditions):
            display_text = f"{condition['column']} {condition['operator']} {condition['value']}"
            self.conditions_list.insert(tk.END, display_text)

    def apply_advanced_filters(self):
        """Apply advanced filters using query builder"""
        if not self.filter_conditions:
            messagebox.showinfo("Info", "No conditions to apply")
            return
            
        try:
            # Build query
            query, params = self.query_builder.build_query(self.filter_conditions)
            
            # Execute query
            if hasattr(self, 'current_file_path') and self.current_file_path.endswith('.duckdb'):
                conn = duckdb.connect(self.current_file_path)
                try:
                    df = conn.execute(query, params).fetchdf()
                    conn.close()
                    
                    # Update display
                    self.setup_smart_columns(df)
                    self.store_original_data(df)
                    
                    # Update treeview
                    self.data_tree.grid_remove()
                    self.data_tree.delete(*self.data_tree.get_children())
                    rows = [tuple(row) for _, row in df.iterrows()]
                    for row in rows:
                        self.data_tree.insert('', 'end', values=row)
                    self.data_tree.grid()
                    
                    messagebox.showinfo("Success", f"Query returned {len(df)} rows")
                    
                except Exception as e:
                    if conn:
                        conn.close()
                    messagebox.showerror("Error", f"Query failed: {str(e)}")
            else:
                messagebox.showerror("Error", "Advanced filtering only available for DuckDB files")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply filters: {str(e)}")

    def clear_advanced_filters(self):
        """Clear all advanced filter conditions"""
        self.filter_conditions = []
        self.update_conditions_display()

    def save_query(self):
        """Save current query to file"""
        if not self.filter_conditions:
            messagebox.showinfo("Info", "No query to save")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=[('JSON files', '*.json')],
            title="Save Query"
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'w') as f:
                    json.dump(self.filter_conditions, f, indent=2)
                messagebox.showinfo("Success", f"Query saved to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save query: {str(e)}")

    def load_query(self):
        """Load query from file"""
        file_path = filedialog.askopenfilename(
            filetypes=[('JSON files', '*.json')],
            title="Load Query"
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'r') as f:
                    self.filter_conditions = json.load(f)
                self.update_conditions_display()
                messagebox.showinfo("Success", f"Query loaded from {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load query: {str(e)}")

    def enable_virtual_scrolling(self):
        """Enable virtual scrolling for better performance with large datasets"""
        if not hasattr(self, 'virtual_tree'):
            # Create virtual scrolling treeview
            tree_frame = self.data_tree.master
            columns = self.data_tree['columns'] if self.data_tree['columns'] else ['col1']
            
            # Store reference to original tree
            self.original_tree = self.data_tree
            
            # Create virtual scrolling treeview
            self.virtual_tree = VirtualScrollingTreeview(tree_frame, columns)
            
            # Replace original tree with virtual tree
            self.data_tree = self.virtual_tree.tree
            
            # Update scrollbars
            if hasattr(self, 'data_view_xscroll'):
                self.data_view_xscroll.config(command=self.data_tree.xview)
                self.data_tree.configure(xscrollcommand=self.data_view_xscroll.set)
            
            if hasattr(self, 'data_view_yscroll'):
                self.data_view_yscroll.config(command=self.data_tree.yview)
                self.data_tree.configure(yscrollcommand=self.data_view_yscroll.set)
            
            # Grid the new tree
            self.data_tree.grid(row=0, column=0, sticky='nsew')
            
            logging.info("Virtual scrolling enabled")

    def load_data_with_virtual_scrolling(self, file_path, format_type):
        """Load data using virtual scrolling for better performance"""
        try:
            # Create data source
            data_source = DataSource(file_path, format_type)
            
            # Enable virtual scrolling if not already enabled
            if not hasattr(self, 'virtual_tree'):
                self.enable_virtual_scrolling()
            
            # Set data source for virtual scrolling
            self.virtual_tree.set_data_source(data_source)
            
            # Setup columns
            if data_source.total_rows > 0:
                sample_row = data_source.get_row(0)
                if sample_row:
                    columns = [f'col{i}' for i in range(len(sample_row))]
                    self.data_tree['columns'] = columns
                    self.data_tree['show'] = 'headings'
                    
                    for i, col in enumerate(columns):
                        self.data_tree.heading(col, text=col)
                        self.data_tree.column(col, width=100)
            
            logging.info(f"Loaded {data_source.total_rows} rows with virtual scrolling")
            
        except Exception as e:
            logging.error(f"Failed to load data with virtual scrolling: {str(e)}")
            messagebox.showerror("Error", f"Failed to load data: {str(e)}")

    def optimize_memory_usage(self):
        """Optimize memory usage for large datasets"""
        try:
            # Clear unnecessary caches
            if hasattr(self, 'cached_data'):
                self.cached_data.clear()
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Update memory usage display
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if hasattr(self, 'memory_label'):
                self.memory_label.config(text=f"Memory: {memory_mb:.1f} MB")
            
            logging.info(f"Memory optimized. Current usage: {memory_mb:.1f} MB")
            
        except Exception as e:
            logging.error(f"Failed to optimize memory: {str(e)}")

    def setup_performance_monitoring(self):
        """Setup performance monitoring for the data viewer"""
        # Create performance monitoring frame
        perf_frame = ttk.LabelFrame(self.root, text="Performance Monitor")
        perf_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)  # Use grid instead of pack
        
        # Memory usage label
        self.memory_label = ttk.Label(perf_frame, text="Memory: 0 MB")
        self.memory_label.pack(side='left', padx=5)
        
        # Performance buttons
        ttk.Button(perf_frame, text="Optimize Memory", 
                  command=self.optimize_memory_usage).pack(side='left', padx=5)
        ttk.Button(perf_frame, text="Enable Virtual Scrolling", 
                  command=self.enable_virtual_scrolling).pack(side='left', padx=5)
        ttk.Button(perf_frame, text="Advanced Filters", 
                  command=self.setup_advanced_filters).pack(side='left', padx=5)
        
        # Start periodic memory monitoring
        self.update_performance_monitor()

    def update_performance_monitor(self):
        """Update performance monitoring display"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if hasattr(self, 'memory_label'):
                self.memory_label.config(text=f"Memory: {memory_mb:.1f} MB")
            
            # Schedule next update
            self.root.after(5000, self.update_performance_monitor)  # Update every 5 seconds
            
        except Exception as e:
            logging.error(f"Failed to update performance monitor: {str(e)}")

    def apply_filters(self):
        """Apply column filters to the data"""
        filters = {}
        for col, entry in self.filter_entries.items():
            value = entry.get().strip()
            if value:
                filters[col] = value.lower()
        
        # Show all items
        self.data_tree.detach(*self.data_tree.get_children())
        items = self.all_items if hasattr(self, 'all_items') else self.data_tree.get_children()
        
        # Apply filters
        for item in items:
            show = True
            for col, filter_value in filters.items():
                value = str(self.data_tree.set(item, col)).lower()
                if filter_value not in value:
                    show = False
                    break
            if show:
                self.data_tree.reattach(item, '', 'end')

    def clear_filters(self):
        """Clear all column filters"""
        for entry in self.filter_entries.values():
            entry.delete(0, tk.END)
        self.apply_filters()

    def get_visible_data(self):
        """Return a DataFrame of the currently visible (filtered/searched) data in the Treeview."""
        columns = self.data_tree['columns']
        data = []
        for item in self.data_tree.get_children():
            values = [self.data_tree.set(item, col) for col in columns]
            data.append(values)
        return pd.DataFrame(data, columns=columns)

    def export_data(self, current_page_only=True):
        """Export visible (filtered/searched) data to file in chosen format."""
        file_types = [
            ('CSV files', '*.csv'),
            ('Excel files', '*.xlsx'),
            ('JSON files', '*.json'),
            ('Parquet files', '*.parquet')
        ]
        file_path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=file_types,
            title="Export Visible Data"
        )
        if not file_path:
            return
        try:
            # Export only visible data
            df = self.get_visible_data()
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.csv':
                df.to_csv(file_path, index=False)
            elif ext == '.xlsx':
                df.to_excel(file_path, index=False)
            elif ext == '.json':
                df.to_json(file_path, orient='records')
            elif ext == '.parquet':
                df.to_parquet(file_path, index=False)
            else:
                messagebox.showerror("Error", f"Unsupported export format: {ext}")
                return
            messagebox.showinfo("Success", f"Exported {len(df)} rows to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export data: {str(e)}")

    def show_view_statistics(self):
        """Show summary statistics for the currently visible (filtered/searched) data."""
        try:
            df = self.get_visible_data()
            if df.empty:
                messagebox.showinfo("Statistics", "No data to show statistics for.")
                return
            stats = df.describe(include='all').T
            stats_str = stats.to_string()
            popup = tk.Toplevel(self.root)
            popup.title("Data Statistics (Visible Data)")
            text = tk.Text(popup, wrap='none', width=120, height=30)
            text.insert('1.0', stats_str)
            text.config(state='disabled')
            text.pack(fill='both', expand=True)
            yscroll = ttk.Scrollbar(popup, orient='vertical', command=text.yview)
            text.configure(yscrollcommand=yscroll.set)
            yscroll.pack(side='right', fill='y')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to show statistics: {str(e)}")

    def show_dataframe_popup(self, df):
        popup = tk.Toplevel(self.root)
        popup.title("File Contents")
        tree = ttk.Treeview(popup, columns=list(df.columns), show='headings')
        for col in df.columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)
        for _, row in df.iterrows():
            tree.insert('', 'end', values=list(row))
        tree.grid(row=0, column=0, sticky='nsew')
        # Add vertical scrollbar
        yscroll = ttk.Scrollbar(popup, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky='ns')
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)

    def refresh_data(self):
        """Refresh the data display"""
        try:
            # Don't clean up scrollbars - reuse existing ones
            # self.cleanup_scrollbars('data_view')  # REMOVED
            
            selection = self.file_listbox.curselection()
            if not selection:
                return
                
            file_path = self.file_listbox.get(selection[0])
            file_path = file_path.split(' [')[0]
            ext = os.path.splitext(file_path)[1].lower()
            fmt = DataLoader.EXT_TO_FORMAT.get(ext, None)
            
            try:
                if fmt == 'keras':
                    # Handle Keras models
                    model = DataLoader.load_file_by_type(file_path, fmt)
                    self.show_keras_model_statistics(model)
                    return
                    
                df = DataLoader.load_file_by_type(file_path, fmt)
                
                # Clear existing data
                self.data_tree.delete(*self.data_tree.get_children())
                
                # Update columns
                cols = list(df.columns)
                self.data_tree['columns'] = cols
                self.data_tree['show'] = 'headings'
                
                # Setup columns
                for col in cols:
                    self.data_tree.heading(col, text=col)
                    self.data_tree.column(col, width=100, stretch=True, anchor='center')
                
                # Add data
                for _, row in df.iterrows():
                    self.data_tree.insert('', 'end', values=tuple(row))
                
                # Update column widths
                for col in cols:
                    self.data_tree.column(col, width=tkFont.Font().measure(col) + 20)
                
                # Scrollbars are already created and configured - no need to recreate them
                # The existing scrollbars will automatically work with the updated treeview
                
            except Exception as e:
                logging.error(f"Failed to refresh data: {str(e)}")
                messagebox.showerror("Error", f"Failed to refresh data: {str(e)}")
                
        except Exception as e:
            logging.error(f"Error in refresh_data: {str(e)}")
            messagebox.showerror("Error", f"Error refreshing data: {str(e)}")

    def preview_selected_loader_file(self):
        selection = self.input_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No file selected")
            return
        file_path = self.input_listbox.get(selection[0])
        print("Previewing file:", file_path)
        # Remove [type] if present
        file_path = file_path.split(' [')[0]
        ext = os.path.splitext(file_path)[1].lower()
        fmt = DataLoader.EXT_TO_FORMAT.get(ext, None)
        try:
            if fmt == 'keras':
                # For Keras, show model summary as text
                try:
                    model = DataLoader.load_file_by_type(file_path, fmt)
                    import io
                    stream = io.StringIO()
                    model.summary(print_fn=lambda x: stream.write(x + '\n'))
                    summary_str = stream.getvalue()
                    popup = tk.Toplevel(self.root)
                    popup.title("Keras Model Summary")
                    text = tk.Text(popup, wrap='word')
                    text.insert('1.0', summary_str)
                    text.pack(fill='both', expand=True)
                    return
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load Keras model: {str(e)}")
                    return
            df = DataLoader.load_file_by_type(file_path, fmt)
            print("DF columns:", df.columns)
            print(df.head())
            self.show_dataframe_popup(df)
        except Exception as e:
            print("Failed to read file:", file_path)
            logging.exception(f"Failed to preview file: {file_path}")
            messagebox.showerror("Error", f"Failed to read file: {str(e)}")

    def preprocess_selected_loader_file(self):
        selection = self.input_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No file selected")
            return
        file_path = self.input_listbox.get(selection[0])
        file_path = file_path.split(' [')[0]
        ext = os.path.splitext(file_path)[1].lower()
        input_format = self.input_format.get()
        fmt = DataLoader.EXT_TO_FORMAT.get(ext, input_format)
        print(f"Preprocessing file: {file_path} as format: {fmt}")
        try:
            if fmt == 'keras':
                try:
                    model = DataLoader.load_file_by_type(file_path, fmt)
                    summary = f"Model inputs: {model.inputs}\nModel outputs: {model.outputs}"
                    messagebox.showinfo("Preprocess Result", summary)
                    return
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load Keras model: {str(e)}")
                    return
            df = DataLoader.load_file_by_type(file_path, fmt)

            # ML Preprocessing: Normalize numeric columns
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if numeric_cols:
                scaler = MinMaxScaler()
                df[numeric_cols] = scaler.fit_transform(df[numeric_cols])

            # Prompt user for save format
            save_format = askstring("Save Format", "Enter save format (json, keras, tensorflow):", initialvalue="json")
            if not save_format:
                messagebox.showinfo("Cancelled", "Save cancelled.")
                return
            save_format = save_format.lower().strip()
            # Prompt for filename
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            save_path = None
            # Use centralized mapping for extension and filetype
            dialog_info = DataLoader.FORMAT_DIALOG_INFO.get(save_format, ('.dat', 'All Files', '*.*'))
            out_ext, desc, pattern = dialog_info
            save_path = filedialog.asksaveasfilename(
                defaultextension=out_ext,
                initialfile=base_name+'_preprocessed'+out_ext,
                filetypes=[(desc, pattern)],
                initialdir='data'
            )
            if not save_path:
                return
            DataLoader.save_file_by_type(df, save_path, save_format)

            # Refresh file list
            self.refresh_file_list()
            messagebox.showinfo("Preprocess & Save", f"Preprocessed data saved as {save_path}")
        except Exception as e:
            logging.exception(f"Failed to preprocess file: {file_path}")
            messagebox.showerror("Error", f"Failed to preprocess file: {str(e)}")

    def remove_selected_file(self):
        def worker():
            selection = self.file_listbox.curselection()
            if not selection:
                self.run_in_main_thread(lambda *a, **k: messagebox.showerror("Error", "No file(s) selected to remove"))
                return
            import os
            removed = 0
            failed = 0
            for idx in reversed(selection):
                file_entry = self.file_listbox.get(idx)
                file_path = file_entry.split(' [')[0]
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        removed += 1
                    else:
                        failed += 1
                except Exception as e:
                    logging.exception(f"Failed to remove file: {file_path}")
                    failed += 1
            def update_gui():
                self.refresh_file_list()
                self.data_tree.delete(*self.data_tree.get_children())
                message = f"Removed {removed} file(s)."
                if failed:
                    message += f" Failed to remove {failed} file(s)."
                messagebox.showinfo("File Removal", message)
            self.run_in_main_thread(lambda *a, **k: update_gui())
        threading.Thread(target=worker, daemon=True).start()

    def run_in_main_thread(self, func, *args, **kwargs):
        # Fix: Properly capture args and kwargs in the lambda
        self.root.after(0, lambda f=func, a=args, k=kwargs: f(*a, **k))

    def show_loader_manual(self):
        guide = (
            """
REDLINE DATA LOADER - QUICK HELP

BASIC OPERATIONS
---------------
1. File Selection
   • Click 'Browse Files' to select data files
   • Use Ctrl/Cmd+Click for multiple files
   • Selected files appear in the list
   • Supported formats: CSV, TXT, JSON, DuckDB, etc.

2. Format Selection
   • Choose Input Format matching your files
   • Select Output Format for conversion
   • Preview files to verify format

3. Data Range & Balancing
   • Set date range (YYYY-MM-DD) to filter data
   • Target Records: Desired records per ticker
   • Minimum Records: Required records threshold
   • Leave blank for automatic values

4. Actions
   • Preview: View file contents
   • Preprocess: Clean and normalize data
   • Merge/Consolidate: Combine multiple files
   • Progress bar shows operation status

TIPS
----
• Always preview files before processing
• Use correct input format to avoid errors
• Check log file for detailed error messages
• Use Parquet/Feather for large datasets

For detailed information, click 'User Manual'
"""
        )

        popup = tk.Toplevel(self.root)
        popup.title("Data Loader Help")
        popup.geometry("600x600")
        
        # Create frame with scrollbar
        frame = ttk.Frame(popup)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add text widget with scrollbar
        text = tk.Text(frame, wrap='word', padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        
        # Pack the text and scrollbar
        text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Insert the guide text
        text.insert('1.0', guide)
        text.config(state='disabled')

    def show_view_manual(self):
        guide = """
REDLINE DATA VIEW - QUICK HELP

BASIC OPERATIONS
---------------
1. File Navigation
   • Browse files in left panel
   • Select files to view/manage
   • Use Refresh to update list
   • Multiple selection enabled

2. Data Display
   • View file contents in table
   • Sort by clicking column headers
   • Navigate with page controls
   • Customize rows per page

3. Ticker Navigation
   • Select tickers from dropdown
   • Use Previous/Next buttons
   • View ticker-specific data
   • Track data coverage

4. Data Management
   • View: Display file contents
   • Remove: Delete selected files
   • Refresh: Update display
   • Export: Save data

FEATURES
--------
• Interactive data table
• Sortable columns
• Pagination controls
• Data statistics
• Export options

TIPS
----
• Use filters to focus on specific data
• Regular refresh keeps view current
• Check data quality indicators
• Monitor file sizes and formats

For detailed information, click 'User Manual'
"""

        popup = tk.Toplevel(self.root)
        popup.title("Data View Help")
        popup.geometry("600x600")
        
        # Create frame with scrollbar
        frame = ttk.Frame(popup)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Add text widget with scrollbar
        text = tk.Text(frame, wrap='word', padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        
        # Pack the text and scrollbar
        text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Insert the guide text
        text.insert('1.0', guide)
        text.config(state='disabled')

    def show_data_statistics(self, data: pd.DataFrame):
        """
        Show comprehensive statistics about the loaded data
        """
        stats = self.loader.analyze_ticker_distribution(data)
        
        stats_text = f"""
DATA STATISTICS REPORT

Overview
--------
Total Records: {stats['total_records']:,}
Total Tickers: {stats['total_tickers']:,}
Average Records/Ticker: {stats['avg_records_per_ticker']:,}

Date Range Coverage
------------------
Earliest Date: {stats['date_ranges']['timestamp']['min']}
Latest Date: {stats['date_ranges']['timestamp']['max']}

Ticker Distribution
------------------
"""
        
        # Add distribution of records per ticker
        records_per_ticker = pd.Series(stats['records_per_ticker'])
        stats_text += f"""
Records per Ticker:
  Minimum: {records_per_ticker.min():,}
  Maximum: {records_per_ticker.max():,}
  Median: {records_per_ticker.median():,}
  Mean: {records_per_ticker.mean():,.2f}
  
Top 5 Tickers by Record Count:
{records_per_ticker.nlargest(5).to_string()}

Bottom 5 Tickers by Record Count:
{records_per_ticker.nsmallest(5).to_string()}
"""
        
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Data Statistics")
        popup.geometry("500x600")
        
        # Add text widget with scrollbar
        text = tk.Text(popup, wrap='word', padx=10, pady=10)
        scrollbar = ttk.Scrollbar(popup, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Insert statistics
        text.insert('1.0', stats_text)
        text.config(state='disabled')

    def setup_bindings(self):
        """Set up event bindings"""
        self.input_listbox.bind('<<ListboxSelect>>', lambda e: self.update_selection_info())

    def analyze_stooq_files(self, file_paths):
        """
        Analyze Stooq data files and return statistics.
        
        Args:
            file_paths (list): List of paths to Stooq data files
            
        Returns:
            dict: Analysis results containing summary and per-file statistics
        """
        analysis = {
            'summary': {
                'total_files': len(file_paths),
                'total_tickers': 0,
                'total_records': 0,
                'earliest_date': None,
                'latest_date': None,
                'avg_records_per_ticker': 0,
                'files_by_size': {
                    'empty': 0,
                    'very_small': 0,  # < 50 records
                    'small': 0,       # < 500 records
                    'medium': 0,      # < 2000 records
                    'large': 0        # >= 2000 records
                }
            },
            'files': {},
            'errors': [],
            'skipped_files': []  # Track skipped files
        }
        
        unique_tickers = set()
        today = pd.Timestamp.now()
        
        for file_path in file_paths:
            try:
                # Convert absolute path to relative path if needed
                relative_path = file_path.replace('/app/', '')
                
                # Check if file exists
                if not os.path.exists(relative_path):
                    analysis['errors'].append({
                        'file': os.path.basename(file_path),
                        'error': 'File not found'
                    })
                    continue
                
                # Check if file is empty
                file_size = os.path.getsize(relative_path)
                if file_size == 0:
                    if delete_empty:
                        try:
                            os.remove(relative_path)
                            logging.info(f"Deleted empty file: {relative_path}")
                        except Exception as e:
                            logging.error(f"Failed to delete empty file {relative_path}: {str(e)}")
                    analysis['summary']['files_by_size']['empty'] += 1
                    analysis['skipped_files'].append({
                        'file': os.path.basename(file_path),
                        'reason': 'Empty file (0 bytes)',
                        'size': 0
                    })
                    logging.warning(f"Skipping empty file: {file_path}")
                    continue
                    
                # Try to read the file
                try:
                    df = pd.read_csv(relative_path)
                    if df.empty:
                        analysis['summary']['files_by_size']['empty'] += 1
                        analysis['skipped_files'].append({
                            'file': os.path.basename(file_path),
                            'reason': 'Empty CSV file (no data rows)',
                            'size': file_size
                        })
                        logging.warning(f"Skipping file with no data rows: {file_path}")
                        continue
                except pd.errors.EmptyDataError:
                    analysis['summary']['files_by_size']['empty'] += 1
                    analysis['skipped_files'].append({
                        'file': os.path.basename(file_path),
                        'reason': 'Empty CSV file (header only)',
                        'size': file_size
                    })
                    logging.warning(f"Skipping empty CSV file: {file_path}")
                    continue
                except Exception as e:
                    analysis['errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Failed to read file: {str(e)}'
                    })
                    logging.error(f"Error reading file {file_path}: {str(e)}")
                    continue
                
                # Check if file has required columns
                required_columns = ['<DATE>', '<TIME>', '<CLOSE>']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    analysis['errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Missing columns: {", ".join(missing_columns)}'
                    })
                    logging.warning(f"File {file_path} missing columns: {missing_columns}")
                    continue
                
                # Extract ticker from filename
                ticker = os.path.basename(file_path).split('.')[0]
                unique_tickers.add(ticker)
                
                # Convert date and time columns to datetime
                try:
                    df['datetime'] = pd.to_datetime(
                        df['<DATE>'].astype(str) + df['<TIME>'].astype(str).str.zfill(6),
                        format='%Y%m%d%H%M%S',
                        errors='coerce'  # Convert invalid dates to NaT
                    )
                    
                    # Check for invalid dates
                    invalid_dates = df[df['datetime'].isna()]
                    if not invalid_dates.empty:
                        analysis['errors'].append({
                            'file': os.path.basename(file_path),
                            'error': f'Contains {len(invalid_dates)} invalid dates'
                        })
                        logging.warning(f"File {file_path} has {len(invalid_dates)} invalid dates")
                    
                    # Remove rows with invalid dates
                    df = df.dropna(subset=['datetime'])
                    if df.empty:
                        analysis['skipped_files'].append({
                            'file': os.path.basename(file_path),
                            'reason': 'No valid dates after cleaning',
                            'size': file_size
                        })
                        logging.warning(f"Skipping file with no valid dates: {file_path}")
                        continue
                    
                except Exception as e:
                    analysis['errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Date parsing error: {str(e)}'
                    })
                    logging.error(f"Date parsing error in {file_path}: {str(e)}")
                    continue
                
                # Check for future dates
                future_dates = df[df['datetime'] > today]
                if not future_dates.empty:
                    analysis['errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Contains {len(future_dates)} future dates (up to {future_dates["datetime"].max().strftime("%Y-%m-%d")})'
                    })
                    logging.warning(f"File {file_path} has {len(future_dates)} future dates")
                
                # Calculate statistics for this file
                records = len(df)
                
                # Update file size statistics
                if records < 50:
                    analysis['summary']['files_by_size']['very_small'] += 1
                elif records < 500:
                    analysis['summary']['files_by_size']['small'] += 1
                elif records < 2000:
                    analysis['summary']['files_by_size']['medium'] += 1
                else:
                    analysis['summary']['files_by_size']['large'] += 1
                
                start_date = df['datetime'].min()
                end_date = df['datetime'].max()
                trading_days = len(df['datetime'].dt.date.unique())
                
                # Calculate gaps (only considering trading days)
                date_range = pd.date_range(start=start_date.date(), end=end_date.date(), freq='B')
                trading_dates = set(df['datetime'].dt.date)
                missing_dates = [d for d in date_range if d not in trading_dates]
                has_gaps = len(missing_dates) > 0
                
                # Calculate price statistics
                price_stats = {
                    'min': df['<CLOSE>'].min(),
                    'max': df['<CLOSE>'].max(),
                    'avg': df['<CLOSE>'].mean()
                }
                
                # Update file statistics
                analysis['files'][file_path] = {
                    'ticker': ticker,
                    'records': records,
                    'trading_days': trading_days,
                    'start_date': start_date,
                    'end_date': end_date,
                    'has_gaps': has_gaps,
                    'gap_count': len(missing_dates),
                    'price_range': price_stats,
                    'has_future_dates': not future_dates.empty,
                    'file_size': file_size
                }
                
                # Update summary statistics
                analysis['summary']['total_records'] += records
                if analysis['summary']['earliest_date'] is None or start_date < analysis['summary']['earliest_date']:
                    analysis['summary']['earliest_date'] = start_date
                if analysis['summary']['latest_date'] is None or end_date > analysis['summary']['latest_date']:
                    analysis['summary']['latest_date'] = end_date
                
            except Exception as e:
                logging.error(f"Error processing {file_path}: {str(e)}")
                analysis['errors'].append({
                    'file': os.path.basename(file_path),
                    'error': str(e)
                })
        
        # Calculate final summary statistics
        analysis['summary']['total_tickers'] = len(unique_tickers)
        if analysis['summary']['total_tickers'] > 0:
            analysis['summary']['avg_records_per_ticker'] = (
                analysis['summary']['total_records'] / analysis['summary']['total_tickers']
            )
        
        return analysis

    def show_stooq_analysis_popup(self, analysis):
        """
        Display analysis results in a popup window
        
        Args:
            analysis (dict): Analysis results from analyze_stooq_files
        """
        popup = tk.Toplevel(self.root)
        popup.title("Stooq Data Analysis")
        popup.geometry("1000x800")
        
        # Create main frame with scrollbar
        main_frame = ttk.Frame(popup)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create notebook for tabbed view
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True)
        
        # Summary tab
        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text='Summary')
        
        summary_text = tk.Text(summary_frame, wrap='word', padx=10, pady=10)
        summary_scroll = ttk.Scrollbar(summary_frame, orient='vertical', command=summary_text.yview)
        summary_text.configure(yscrollcommand=summary_scroll.set)
        
        summary_text.pack(side='left', fill='both', expand=True)
        summary_scroll.pack(side='right', fill='y')
        
        # Format and insert summary text
        summary = "ANALYSIS SUMMARY\n===============\n\n"
        summary += f"Total Files: {analysis['summary']['total_files']:,}\n"
        summary += f"Total Tickers: {analysis['summary']['total_tickers']:,}\n"
        summary += f"Total Records: {analysis['summary']['total_records']:,}\n"
        
        if analysis['summary']['earliest_date'] and analysis['summary']['latest_date']:
            summary += f"Date Range: {analysis['summary']['earliest_date'].strftime('%Y-%m-%d')} to "
            summary += f"{analysis['summary']['latest_date'].strftime('%Y-%m-%d')}\n"
        
        summary += f"Average Records per Ticker: {analysis['summary']['avg_records_per_ticker']:,.2f}\n\n"
        
        # Add file size distribution
        summary += "FILE SIZE DISTRIBUTION\n--------------------\n"
        summary += f"Empty Files: {analysis['summary']['files_by_size']['empty']}\n"
        summary += f"Very Small Files (<50 records): {analysis['summary']['files_by_size']['very_small']}\n"
        summary += f"Small Files (<500 records): {analysis['summary']['files_by_size']['small']}\n"
        summary += f"Medium Files (<2000 records): {analysis['summary']['files_by_size']['medium']}\n"
        summary += f"Large Files (≥2000 records): {analysis['summary']['files_by_size']['large']}\n\n"
        
        # Add error summary if any errors occurred
        if analysis['errors']:
            summary += f"ERRORS AND WARNINGS\n-----------------\n"
            summary += f"Errors encountered in {len(analysis['errors'])} files\n"
        
        if analysis['skipped_files']:
            summary += f"\nSKIPPED FILES\n-------------\n"
            for skip in analysis['skipped_files']:
                summary += f"• {skip['file']}: {skip['reason']}\n"
        
        summary_text.insert('1.0', summary)
        summary_text.config(state='disabled')
        
        # Details tab
        details_frame = ttk.Frame(notebook)
        notebook.add(details_frame, text='Details')
        
        details_text = tk.Text(details_frame, wrap='word', padx=10, pady=10)
        details_scroll = ttk.Scrollbar(details_frame, orient='vertical', command=details_text.yview)
        details_text.configure(yscrollcommand=details_scroll.set)
        
        details_text.pack(side='left', fill='both', expand=True)
        details_scroll.pack(side='right', fill='y')
        
        # Format and insert details
        details = self.format_analysis_details(analysis)
        details_text.insert('1.0', details)
        details_text.config(state='disabled')

    def format_analysis_details(self, analysis):
        """
        Format detailed analysis data
        
        Args:
            analysis (dict): Analysis results from analyze_stooq_files
            
        Returns:
            str: Formatted details text
        """
        details = "DETAILED FILE ANALYSIS\n=====================\n\n"
        
        # Sort files by record count
        sorted_files = sorted(
            analysis['files'].items(),
            key=lambda x: x[1]['records'],
            reverse=True
        )
        
        for file_path, stats in sorted_files:
            details += f"File: {os.path.basename(file_path)}\n"
            details += f"Ticker: {stats['ticker']}\n"
            details += f"Records: {stats['records']:,}\n"
            details += f"Trading Days: {stats['trading_days']}\n"
            details += f"Date Range: {stats['start_date'].strftime('%Y-%m-%d')} to {stats['end_date'].strftime('%Y-%m-%d')}\n"
            details += f"Has Gaps: {'Yes' if stats['has_gaps'] else 'No'} ({stats['gap_count']} gaps)\n"
            details += f"Price Range: ${stats['price_range']['min']:.2f} - ${stats['price_range']['max']:.2f}"
            details += f" (avg: ${stats['price_range']['avg']:.2f})\n"
            details += "-" * 50 + "\n\n"
        
        if analysis['errors']:
            details += "\nERRORS ENCOUNTERED\n------------------\n"
            for error in analysis['errors']:
                details += f"File: {os.path.basename(error['file'])}\n"
                details += f"Error: {error['error']}\n\n"
        
        return details

    def analyze_selected_files_timestamps(self, file_paths, input_format):
        """
        Analyze timestamps in selected files before loading.
        
        Args:
            file_paths (list): List of paths to data files
            input_format (str): Input format of the files
            
        Returns:
            dict: Summary of timestamp analysis
        """
        summary = {
            'total_files': len(file_paths),
            'processed_files': 0,
            'earliest_date': None,
            'latest_date': None,
            'files_with_errors': [],
            'invalid_dates': [],
            'future_dates': []
        }
        
        today = pd.Timestamp.now()
        
        for file_path in file_paths:
            try:
                # Convert absolute path to relative path if needed
                relative_path = file_path.replace('/app/', '')
                
                # Skip empty files
                if os.path.getsize(relative_path) == 0:
                    summary['files_with_errors'].append({
                        'file': os.path.basename(file_path),
                        'error': 'Empty file'
                    })
                    continue
                
                # Read the file
                df = pd.read_csv(relative_path)
                
                # Check for required columns based on format
                if input_format.lower() == 'stooq':
                    date_col = '<DATE>'
                    time_col = '<TIME>'
                    required_cols = [date_col, time_col]
                else:
                    # For other formats, assume 'timestamp' column
                    date_col = 'timestamp'
                    required_cols = [date_col]
                
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    summary['files_with_errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Missing columns: {", ".join(missing_cols)}'
                    })
                    continue
                
                # Convert dates based on format
                try:
                    if input_format.lower() == 'stooq':
                        # Combine date and time columns
                        df['datetime'] = pd.to_datetime(
                            df[date_col].astype(str) + df[time_col].astype(str).str.zfill(6),
                            format='%Y%m%d%H%M%S'
                        )
                    else:
                        # Assume timestamp is already in datetime format
                        df['datetime'] = pd.to_datetime(df[date_col])
                    
                    # Check for invalid dates
                    invalid_dates = df[df['datetime'].isna()]
                    if not invalid_dates.empty:
                        summary['invalid_dates'].append({
                            'file': os.path.basename(file_path),
                            'count': len(invalid_dates),
                            'rows': invalid_dates.index.tolist()[:5]  # First 5 invalid rows
                        })
                    
                    # Check for future dates
                    future_dates = df[df['datetime'] > today]
                    if not future_dates.empty:
                        summary['future_dates'].append({
                            'file': os.path.basename(file_path),
                            'count': len(future_dates),
                            'max_date': future_dates['datetime'].max()
                        })
                    
                    # Update date range
                    file_min_date = df['datetime'].min()
                    file_max_date = df['datetime'].max()
                    
                    if summary['earliest_date'] is None or file_min_date < summary['earliest_date']:
                        summary['earliest_date'] = file_min_date
                    if summary['latest_date'] is None or file_max_date > summary['latest_date']:
                        summary['latest_date'] = file_max_date
                    
                    summary['processed_files'] += 1
                    
                except Exception as e:
                    summary['files_with_errors'].append({
                        'file': os.path.basename(file_path),
                        'error': f'Date parsing error: {str(e)}'
                    })
                    
            except Exception as e:
                summary['files_with_errors'].append({
                    'file': os.path.basename(file_path),
                    'error': str(e)
                })
        
        return summary

    def show_timestamp_analysis_popup(self, summary):
        """
        Display timestamp analysis results in a popup window.
        
        Args:
            summary (dict): Results from analyze_selected_files_timestamps
        """
        popup = tk.Toplevel(self.root)
        popup.title("Timestamp Analysis")
        popup.geometry("800x600")
        
        # Create text widget with scrollbar
        text = tk.Text(popup, wrap='word', padx=10, pady=10)
        scrollbar = ttk.Scrollbar(popup, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        
        text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Format analysis results
        result = "TIMESTAMP ANALYSIS\n=================\n\n"
        
        # Overall statistics
        result += f"Total Files: {summary['total_files']}\n"
        result += f"Successfully Processed: {summary['processed_files']}\n"
        
        if summary['earliest_date'] and summary['latest_date']:
            result += f"\nDate Range:\n"
            result += f"Earliest: {summary['earliest_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            result += f"Latest: {summary['latest_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # Invalid dates
        if summary['invalid_dates']:
            result += f"\nINVALID DATES\n-------------\n"
            for invalid in summary['invalid_dates']:
                result += f"• {invalid['file']}: {invalid['count']} invalid dates\n"
                result += f"  First {len(invalid['rows'])} invalid rows: {invalid['rows']}\n"
        
        # Future dates
        if summary['future_dates']:
            result += f"\nFUTURE DATES\n------------\n"
            for future in summary['future_dates']:
                result += f"• {future['file']}: {future['count']} future dates\n"
                result += f"  Latest date: {future['max_date'].strftime('%Y-%m-%d')}\n"
        
        # Errors
        if summary['files_with_errors']:
            result += f"\nERRORS\n------\n"
            for error in summary['files_with_errors']:
                result += f"• {error['file']}: {error['error']}\n"
        
        text.insert('1.0', result)
        text.config(state='disabled')

    def show_keras_model_statistics(self, model):
        """Show statistics for a Keras model"""
        try:
            # Create popup window
            popup = tk.Toplevel(self.root)
            popup.title("Keras Model Statistics")
            popup.geometry("600x800")
            
            # Add text widget with scrollbar
            text = tk.Text(popup, wrap='word', padx=10, pady=10)
            scrollbar = ttk.Scrollbar(popup, orient='vertical', command=text.yview)
            text.configure(yscrollcommand=scrollbar.set)
            
            # Pack widgets
            text.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Generate model statistics
            stats_text = "KERAS MODEL STATISTICS\n=====================\n\n"
            
            # Basic model info
            stats_text += "Model Structure:\n----------------\n"
            for i, layer in enumerate(model.layers):
                stats_text += f"Layer {i}: {layer.__class__.__name__}\n"
                # Get layer config safely
                config = layer.get_config()
                if 'units' in config:
                    stats_text += f"  Units: {config['units']}\n"
                if 'activation' in config:
                    stats_text += f"  Activation: {config['activation']}\n"
                stats_text += f"  Parameters: {layer.count_params():,}\n\n"
            
            # Total parameters
            stats_text += f"\nTotal Parameters: {model.count_params():,}\n"
            
            # Model configuration
            stats_text += "\nModel Configuration:\n-------------------\n"
            if hasattr(model, 'optimizer'):
                stats_text += f"Optimizer: {model.optimizer.__class__.__name__ if model.optimizer else 'Not compiled'}\n"
            if hasattr(model, 'loss'):
                stats_text += f"Loss Function: {model.loss if model.loss else 'Not compiled'}\n"
            
            # Insert text and disable editing
            text.insert('1.0', stats_text)
            text.config(state='disabled')
            
        except Exception as e:
            logging.error(f"Failed to show Keras model statistics: {str(e)}")
            messagebox.showerror("Error", f"Failed to show model statistics: {str(e)}")

    def show_statistics_popup(self, stats):
        """Show general statistics in a popup window"""
        try:
            # Create popup window
            popup = tk.Toplevel(self.root)
            popup.title("Data Statistics")
            popup.geometry("800x600")
            
            # Create notebook for tabbed view
            notebook = ttk.Notebook(popup)
            notebook.pack(fill='both', expand=True, padx=5, pady=5)
            
            # Summary tab
            summary_frame = ttk.Frame(notebook)
            notebook.add(summary_frame, text='Summary')
            
            summary_text = tk.Text(summary_frame, wrap='word', padx=10, pady=10)
            summary_scroll = ttk.Scrollbar(summary_frame, orient='vertical', command=summary_text.yview)
            summary_text.configure(yscrollcommand=summary_scroll.set)
            
            summary_text.pack(side='left', fill='both', expand=True)
            summary_scroll.pack(side='right', fill='y')
            
            # Format summary text
            summary = "DATA STATISTICS SUMMARY\n=====================\n\n"
            
            # Basic statistics
            summary += "Basic Information:\n-----------------\n"
            for key, value in stats['basic'].items():
                summary += f"{key}: {value}\n"
            
            # Date range if available
            if stats['date_range']:
                summary += "\nDate Range:\n-----------\n"
                summary += f"Start: {stats['date_range']['start']}\n"
                summary += f"End: {stats['date_range']['end']}\n"
                summary += f"Unique Periods: {stats['date_range']['periods']}\n"
            
            summary_text.insert('1.0', summary)
            summary_text.config(state='disabled')
            
            # Columns tab
            columns_frame = ttk.Frame(notebook)
            notebook.add(columns_frame, text='Column Details')
            
            columns_text = tk.Text(columns_frame, wrap='word', padx=10, pady=10)
            columns_scroll = ttk.Scrollbar(columns_frame, orient='vertical', command=columns_text.yview)
            columns_text.configure(yscrollcommand=columns_scroll.set)
            
            columns_text.pack(side='left', fill='both', expand=True)
            columns_scroll.pack(side='right', fill='y')
            
            # Format columns text
            columns_detail = "COLUMN DETAILS\n==============\n\n"
            
            for col, col_stats in stats['columns'].items():
                columns_detail += f"Column: {col}\n{'-' * (len(col) + 8)}\n"
                for stat_name, stat_value in col_stats.items():
                    if isinstance(stat_value, float):
                        columns_detail += f"{stat_name}: {stat_value:.4f}\n"
                    else:
                        columns_detail += f"{stat_name}: {stat_value}\n"
                columns_detail += "\n"
            
            columns_text.insert('1.0', columns_detail)
            columns_text.config(state='disabled')
            
        except Exception as e:
            logging.error(f"Failed to show statistics popup: {str(e)}")
            messagebox.showerror("Error", f"Failed to show statistics popup: {str(e)}")

    def safe_update_widget(self, widget_name, update_func):
        """Safely update a widget from background thread"""
        if hasattr(self, widget_name):
            widget = getattr(self, widget_name)
            if widget and widget.winfo_exists():
                def safe_update():
                    with self.ui_lock:
                        update_func()
                self.run_in_main_thread(safe_update)
            else:
                logging.warning(f"Widget {widget_name} does not exist or has been destroyed")
        else:
            logging.warning(f"Widget {widget_name} not found")

    def batch_ui_update(self, updates):
        """Execute multiple UI updates in a single main thread call to reduce race conditions"""
        def batch_update():
            with self.ui_lock:
                for update_func in updates:
                    try:
                        update_func()
                    except Exception as e:
                        logging.error(f"Error in batch UI update: {str(e)}")
        self.run_in_main_thread(batch_update)

    def safe_batch_update(self, updates):
        """Safely execute multiple UI updates with widget existence checks"""
        def safe_batch():
            with self.ui_lock:
                for widget_name, update_func in updates:
                    if hasattr(self, widget_name):
                        widget = getattr(self, widget_name)
                        if widget and widget.winfo_exists():
                            try:
                                update_func()
                            except Exception as e:
                                logging.error(f"Error updating {widget_name}: {str(e)}")
                        else:
                            logging.warning(f"Widget {widget_name} does not exist or has been destroyed")
                    else:
                        logging.warning(f"Widget {widget_name} not found")
        self.run_in_main_thread(safe_batch)

    def update_file_status_label(self, event=None):
        selection = self.file_listbox.curselection()
        if selection:
            file_path = self.file_listbox.get(selection[0])
            file_name = os.path.basename(file_path.split(' [')[0])
            file_format = file_path.split(' [')[1].rstrip(']') if ' [' in file_path else ''
            try:
                file_size = os.path.getsize(file_path.split(' [')[0])
                size_str = f"{file_size/1024:.1f} KB" if file_size < 1024*1024 else f"{file_size/1024/1024:.2f} MB"
            except Exception:
                size_str = "-"
            status_text = f"Selected: {file_name} | Format: {file_format} | Size: {size_str}"
            self.file_status_label.config(text=status_text, foreground="green")
        else:
            self.file_status_label.config(text="No file selected", foreground="gray")

    def on_search_change(self, event=None):
        """Handle search text changes"""
        search_text = self.search_var.get()
        if not search_text:
            # Show all items if search is empty
            self.show_all_items()
            self.search_results_label.config(text="")
            return
        
        # Get all items from the tree
        all_items = self.data_tree.get_children()
        if not all_items:
            return
        
        # Hide all items first
        self.data_tree.detach(*all_items)
        
        # Search through items
        matched_items = []
        case_sensitive = self.search_case_sensitive.get()
        
        for item in all_items:
            values = self.data_tree.item(item)['values']
            item_text = ' '.join(str(v) for v in values)
            
            if case_sensitive:
                if search_text in item_text:
                    matched_items.append(item)
            else:
                if search_text.lower() in item_text.lower():
                    matched_items.append(item)
        
        # Show matched items
        for item in matched_items:
            self.data_tree.reattach(item, '', 'end')
        
        # Update search results label
        total_items = len(all_items)
        matched_count = len(matched_items)
        self.search_results_label.config(text=f"Found {matched_count} of {total_items} items")

    def clear_search(self):
        """Clear search and show all items"""
        self.search_var.set("")
        
        # Repopulate treeview with original data
        if hasattr(self, 'original_data') and self.original_data is not None:
            self.data_tree.delete(*self.data_tree.get_children())
            for _, row in self.original_data.iterrows():
                self.data_tree.insert('', 'end', values=tuple(row))
        
        self.search_results_label.config(text="")

    def show_all_items(self):
        """Show all items in the treeview"""
        all_items = self.data_tree.get_children()
        if not all_items:
            return
        
        # Reattach all items
        for item in all_items:
            self.data_tree.reattach(item, '', 'end')

    def store_original_data(self, df):
        """Store original data for searching and filtering"""
        self.original_data = df.copy()
        self.current_data = df.copy()

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common actions"""
        # Bind keyboard shortcuts to the root window
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        self.root.bind('<Control-e>', lambda e: self.export_data())
        self.root.bind('<Control-r>', lambda e: self.refresh_file_list())
        self.root.bind('<Control-s>', lambda e: self.show_view_statistics())
        self.root.bind('<Control-v>', lambda e: self.view_selected_file())
        self.root.bind('<Control-d>', lambda e: self.remove_selected_file())
        self.root.bind('<Escape>', lambda e: self.clear_search())
        self.root.bind('<F5>', lambda e: self.refresh_file_list())
        
        # Add tooltips with shortcut hints
        self.add_shortcut_tooltips()

    def add_shortcut_tooltips(self):
        """Add tooltips with shortcut hints to buttons"""
        # Create tooltip function
        def create_tooltip(widget, text):
            def show_tooltip(event):
                tooltip = tk.Toplevel()
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
                
                label = tk.Label(tooltip, text=text, justify='left',
                               background="#ffffe0", relief='solid', borderwidth=1)
                label.pack()
                
                def hide_tooltip(event):
                    tooltip.destroy()
                
                widget.bind('<Leave>', hide_tooltip)
                tooltip.bind('<Leave>', hide_tooltip)
                tooltip.bind('<Button-1>', hide_tooltip)
            
            widget.bind('<Enter>', show_tooltip)
        
        # Add tooltips to buttons (we'll need to find them by traversing the widget tree)
        self.add_tooltips_to_buttons()

    def add_tooltips_to_buttons(self):
        """Add tooltips to buttons throughout the interface"""
        # This is a simplified version - in a full implementation, you'd traverse the widget tree
        # and add tooltips to specific buttons
        pass

    def focus_search(self):
        """Focus the search entry"""
        if hasattr(self, 'search_entry'):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)

    def validate_data_file(self, file_path, format_type):
        """Validate data file before loading"""
        try:
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
            
            if os.path.getsize(file_path) == 0:
                raise ValueError(f"File is empty: {file_path}")
            
            # Check file extension matches format
            ext = os.path.splitext(file_path)[1].lower()
            expected_ext = DataLoader.EXT_TO_FORMAT.get(ext, None)
            if expected_ext and expected_ext != format_type:
                raise ValueError(f"File extension '{ext}' doesn't match format '{format_type}'")
            
            return True
            
        except Exception as e:
            self.show_enhanced_error("Data Validation Error", str(e), file_path)
            return False

    def show_enhanced_error(self, title, message, file_path=None):
        """Show enhanced error message with suggestions"""
        error_window = tk.Toplevel(self.root)
        error_window.title(title)
        error_window.geometry("500x300")
        error_window.resizable(True, True)
        
        # Main error message
        error_frame = ttk.Frame(error_window)
        error_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Label(error_frame, text="Error Details:", font=('Arial', 12, 'bold')).pack(anchor='w')
        
        # Error message text
        error_text = tk.Text(error_frame, height=8, wrap='word')
        error_text.pack(fill='both', expand=True, pady=(5, 10))
        error_text.insert('1.0', message)
        error_text.config(state='disabled')
        
        # File path if provided
        if file_path:
            ttk.Label(error_frame, text=f"File: {file_path}", foreground='gray').pack(anchor='w')
        
        # Suggestions frame
        suggestions_frame = ttk.LabelFrame(error_frame, text="Suggestions")
        suggestions_frame.pack(fill='x', pady=(10, 0))
        
        suggestions = self.get_error_suggestions(message, file_path)
        for suggestion in suggestions:
            ttk.Label(suggestions_frame, text=f"• {suggestion}", wraplength=450).pack(anchor='w', padx=5, pady=2)
        
        # Buttons
        button_frame = ttk.Frame(error_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(button_frame, text="Copy Error", 
                  command=lambda: self.copy_to_clipboard(message)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Close", 
                  command=error_window.destroy).pack(side='right', padx=5)

    def get_error_suggestions(self, error_message, file_path=None):
        """Get suggestions based on error message"""
        suggestions = []
        
        if "File not found" in error_message:
            suggestions.extend([
                "Check if the file path is correct",
                "Verify the file exists in the specified location",
                "Try using the file browser to select the file"
            ])
        elif "File is empty" in error_message:
            suggestions.extend([
                "Check if the file contains data",
                "Verify the file wasn't corrupted during transfer",
                "Try opening the file in a text editor to verify content"
            ])
        elif "format" in error_message.lower():
            suggestions.extend([
                "Check if the file format is supported",
                "Verify the file extension matches the content",
                "Try converting the file to a supported format"
            ])
        elif "permission" in error_message.lower():
            suggestions.extend([
                "Check file permissions",
                "Try running the application with elevated privileges",
                "Verify you have read access to the file"
            ])
        else:
            suggestions.extend([
                "Check the file format and content",
                "Verify all required dependencies are installed",
                "Try refreshing the file list"
            ])
        
        return suggestions

    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Error message copied to clipboard")

    def setup_bindings(self):
        """Setup additional bindings for better user experience"""
        # File listbox bindings
        self.file_listbox.bind('<Double-Button-1>', lambda e: self.view_selected_file())
        self.file_listbox.bind('<Return>', lambda e: self.view_selected_file())
        self.file_listbox.bind('<Delete>', lambda e: self.remove_selected_file())
        
        # Search entry bindings
        if hasattr(self, 'search_entry'):
            self.search_entry.bind('<Return>', lambda e: self.on_search_change())
            self.search_entry.bind('<Control-a>', lambda e: self.select_all_search())
        
        # Data tree bindings
        self.data_tree.bind('<Control-a>', lambda e: self.select_all_tree())
        self.data_tree.bind('<Control-c>', lambda e: self.copy_selected_tree_items())

    def select_all_search(self):
        """Select all text in search entry"""
        self.search_entry.select_range(0, tk.END)
        return 'break'

    def select_all_tree(self):
        """Select all items in tree"""
        for item in self.data_tree.get_children():
            self.data_tree.selection_add(item)
        return 'break'

    def copy_selected_tree_items(self):
        """Copy selected tree items to clipboard"""
        selected_items = self.data_tree.selection()
        if not selected_items:
            return 'break'
        
        # Get column headers
        columns = self.data_tree['columns']
        
        # Build CSV-like string
        csv_data = '\t'.join(columns) + '\n'
        for item in selected_items:
            values = [self.data_tree.set(item, col) for col in columns]
            csv_data += '\t'.join(str(v) for v in values) + '\n'
        
        self.root.clipboard_clear()
        self.root.clipboard_append(csv_data)
        return 'break'

def run(task: str = 'gui'):
    loader = DataLoader()
    connector = DatabaseConnector(loader.db_path)
    if task == 'gui':
        root = tk.Tk()
        app = StockAnalyzerGUI(root, loader, connector)
        root.mainloop()
    elif task in ['load', 'convert', 'preprocess']:
        # Example for load task
        if task == 'load':
            pass  # Removed loading of sample.csv
        logging.info(f"Completed task: {task}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', default='gui', choices=['gui', 'load', 'convert', 'preprocess'])
    args = parser.parse_args()
    run(args.task) 