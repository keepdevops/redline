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
        # Ensure all schema columns are present
        for col in DataLoader.SCHEMA:
            if col not in data.columns:
                data[col] = None
        data = data[DataLoader.SCHEMA]
        # Clean numeric columns to ensure no arrays/lists and cast to float
        for col in ['open', 'high', 'low', 'close', 'vol', 'openint']:
            if col in data.columns:
                data[col] = data[col].apply(lambda x: float(x) if pd.notnull(x) and not isinstance(x, (list, tuple, dict)) else None)
        return data

    def __init__(self, config_path: str = 'data_config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.db_path = self.config['Data'].get('db_path', '/app/redline_data.duckdb')
        self.csv_dir = self.config['Data'].get('csv_dir', '/app/data')
        self.json_dir = self.config['Data'].get('json_dir', '/app/data/json')
        self.parquet_dir = self.config['Data'].get('parquet_dir', '/app/data/parquet')

    def load_data(self, file_paths: List[str], format: str) -> List[Union[pd.DataFrame, pl.DataFrame, pa.Table]]:
        data = []
        for path in file_paths:
            if not self.validate_data(path, format):
                raise ValueError(f"Invalid data in {path} for format {format}")
            try:
                if format == 'csv':
                    df = pd.read_csv(path)
                elif format == 'txt':
                    df = pd.read_csv(path, delimiter='\t')
                    if df.shape[1] == 1:
                        df = pd.read_csv(path, delimiter=',')
                    df = self._standardize_txt_columns(df)
                    print(f'Loaded DataFrame shape: {df.shape}')
                elif format == 'json':
                    df = pd.read_json(path)
                elif format == 'duckdb':
                    conn = duckdb.connect(path)
                    df = conn.execute("SELECT * FROM tickers_data").fetchdf()
                    conn.close()
                elif format == 'pyarrow':
                    df = pa.parquet.read_table(path)
                elif format == 'polars':
                    df = pl.read_parquet(path)
                elif format == 'keras':
                    df = tf.keras.models.load_model(path)
                else:
                    df = None
                if format in ['csv', 'txt', 'json', 'duckdb']:
                    data.append(df)
                else:
                    data.append(df)
                logging.info(f"Loaded {path} as {format}")
            except Exception as e:
                logging.error(f"Failed to load {path}: {str(e)}")
                print(f"Failed to load {path}: {str(e)}")
                raise
        return data

    def validate_data(self, file_path: str, format: str) -> bool:
        try:
            if format in ['csv', 'json', 'txt']:
                if format == 'csv':
                    df = pd.read_csv(file_path)
                elif format == 'txt':
                    df = pd.read_csv(file_path, delimiter='\t')
                    if df.shape[1] == 1:
                        df = pd.read_csv(file_path, delimiter=',')
                    df = self._standardize_txt_columns(df)
                else:
                    df = pd.read_json(file_path)
                required = ['ticker', 'timestamp', 'close']
                return all(col in df.columns for col in required)
            return True  # Simplified for other formats
        except Exception as e:
            logging.error(f"Validation failed for {file_path}: {str(e)}")
            print(f"Validation failed for {file_path}: {str(e)}")
            return False

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
                timestamp VARCHAR,
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

    def _standardize_txt_columns(self, df):
        print('Original columns:', list(df.columns))
        # Remove BOM and strip whitespace from column names
        df.columns = [c.lstrip('\ufeff').strip() for c in df.columns]
        col_map = {}
        for c in df.columns:
            cl = c.strip('<>').strip().upper()
            if cl == 'TICKER':
                col_map[c] = 'ticker'
            elif cl == 'PER':
                col_map[c] = 'per'
            elif cl == 'DATE':
                col_map[c] = 'date'
            elif cl == 'TIME':
                col_map[c] = 'time'
            elif cl == 'CLOSE':
                col_map[c] = 'close'
            elif cl == 'OPEN':
                col_map[c] = 'open'
            elif cl == 'HIGH':
                col_map[c] = 'high'
            elif cl == 'LOW':
                col_map[c] = 'low'
            elif cl == 'VOL':
                col_map[c] = 'vol'
            elif cl == 'OPENINT':
                col_map[c] = 'openint'
        df = df.rename(columns=col_map)
        print('Mapped columns:', list(df.columns))
        # Combine date and time into timestamp if present
        if 'date' in df.columns and 'time' in df.columns:
            df['timestamp'] = df['date'].astype(str) + ' ' + df['time'].astype(str)
        elif 'date' in df.columns:
            df['timestamp'] = df['date'].astype(str)
        # Define the columns you want to keep
        keep = [c for c in ['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'vol', 'openint'] if c in df.columns]
        # Drop 'date', 'time', and 'per' columns after creating 'timestamp', but only if not in keep
        for col in ['date', 'time', 'per']:
            if col in df.columns and col not in keep:
                df = df.drop(columns=[col])
        # Now select only the columns you want to keep
        df = df[keep]
        if all(k in df.columns for k in ['ticker', 'timestamp', 'close']):
            return df
        return df

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
                timestamp VARCHAR,
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

class StockAnalyzerGUI:
    def __init__(self, root: tk.Tk, loader: DataLoader, connector: DatabaseConnector):
        self.root = root
        self.root.title("REDLINE Data Conversion Utility")
        
        # Set minimum window size
        self.root.minsize(1200, 800)  # Increased from default size
        
        # Configure main window grid weights
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        self.loader = loader
        self.connector = connector
        self.adapter = DataAdapter()
        
        # Create main notebook with larger size
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.setup_tabs()
        self.setup_bindings()

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
        
        # Increased listbox size
        self.input_listbox = tk.Listbox(file_group, selectmode='multiple', width=50, height=15)
        self.input_listbox.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Add scrollbars to listbox
        listbox_scroll_y = ttk.Scrollbar(self.input_listbox, orient='vertical', command=self.input_listbox.yview)
        listbox_scroll_x = ttk.Scrollbar(self.input_listbox, orient='horizontal', command=self.input_listbox.xview)
        self.input_listbox.configure(yscrollcommand=listbox_scroll_y.set, xscrollcommand=listbox_scroll_x.set)
        
        listbox_scroll_y.pack(side='right', fill='y')
        listbox_scroll_x.pack(side='bottom', fill='x')

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

        # Left: File list and action buttons
        left_frame = ttk.Frame(view_frame)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky='ns')
        ttk.Label(left_frame, text="Available Data Files:").grid(row=0, column=0, sticky='w')
        self.file_listbox = tk.Listbox(left_frame, width=40, selectmode='extended', height=12)
        self.file_listbox.grid(row=1, column=0, sticky='nsew', pady=5)
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=2, column=0, pady=5, sticky='ew')
        ttk.Button(btn_frame, text="View File", command=self.view_selected_file).grid(row=0, column=0, padx=2)
        ttk.Button(btn_frame, text="Remove File", command=self.remove_selected_file).grid(row=0, column=1, padx=2)
        ttk.Button(btn_frame, text="Refresh Data", command=self.refresh_data).grid(row=0, column=2, padx=2)
        view_help_btn = ttk.Button(btn_frame, text='?', width=2, command=self.show_view_manual)
        view_help_btn.grid(row=0, column=3, padx=2)
        # User Manual button now grouped with other buttons
        view_manual_btn = ttk.Button(btn_frame, text='User Manual', command=lambda: show_user_manual_popup(self.root))
        view_manual_btn.grid(row=0, column=4, padx=2)

        # Right: Data table with scrollbars
        right_frame = ttk.Frame(view_frame)
        right_frame.grid(row=0, column=1, padx=10, pady=10, sticky='nsew')
        tree_frame = ttk.Frame(right_frame)
        tree_frame.grid(row=0, column=0, sticky='nsew')
        xscroll = ttk.Scrollbar(tree_frame, orient='horizontal')
        yscroll = ttk.Scrollbar(tree_frame, orient='vertical')
        self.data_tree = ttk.Treeview(tree_frame, columns=['Ticker', 'Date', 'Close', 'Format'], show='headings', xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        xscroll.config(command=self.data_tree.xview)
        yscroll.config(command=self.data_tree.yview)
        self.data_tree.grid(row=0, column=0, sticky='nsew')
        xscroll.grid(row=1, column=0, sticky='ew')
        yscroll.grid(row=0, column=1, sticky='ns')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # Configure main view_frame grid
        view_frame.grid_rowconfigure(0, weight=1)
        view_frame.grid_columnconfigure(0, weight=0)
        view_frame.grid_columnconfigure(1, weight=1)

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
        
        class AnalysisWorker:
            def __init__(self, parent, files):
                self.parent = parent
                self.files = files
                self.error = None
                self.analysis_result = None
            
            def show_progress(self):
                self.parent.progress_bar.pack()
                self.parent.progress_var.set(10)
            
            def hide_progress(self):
                self.parent.progress_bar.pack_forget()
            
            def show_error(self):
                if self.error:
                    messagebox.showerror("Error", f"Analysis failed: {str(self.error)}")
            
            def update_gui(self):
                if not self.analysis_result:
                    return
                
                try:
                    # Show analysis popup
                    self.parent.show_stooq_analysis_popup(self.analysis_result)
                    
                    # Update date range entries
                    if (self.analysis_result['summary']['earliest_date'] and 
                        self.analysis_result['summary']['latest_date']):
                        self.parent.start_date_entry.delete(0, tk.END)
                        self.parent.start_date_entry.insert(0, 
                            self.analysis_result['summary']['earliest_date'].strftime('%Y-%m-%d'))
                        self.parent.end_date_entry.delete(0, tk.END)
                        self.parent.end_date_entry.insert(0, 
                            self.analysis_result['summary']['latest_date'].strftime('%Y-%m-%d'))
                    
                    # Update record count entries
                    if (self.analysis_result['summary']['total_records'] and 
                        self.analysis_result['summary']['total_tickers']):
                        avg_records = (self.analysis_result['summary']['total_records'] // 
                                     self.analysis_result['summary']['total_tickers'])
                        self.parent.target_records_entry.delete(0, tk.END)
                        self.parent.target_records_entry.insert(0, str(avg_records))
                        self.parent.min_records_entry.delete(0, tk.END)
                        self.parent.min_records_entry.insert(0, str(avg_records // 2))
                
                except Exception as gui_error:
                    logging.error(f"Error updating GUI: {str(gui_error)}")
                    messagebox.showerror("Error", f"Failed to update GUI: {str(gui_error)}")
            
            def run(self):
                try:
                    # Show progress
                    self.parent.run_in_main_thread(self.show_progress)
                    
                    # Perform analysis
                    self.analysis_result = self.parent.analyze_stooq_files(self.files)
                    
                    # Update GUI with results
                    self.parent.run_in_main_thread(self.update_gui)
                    
                except Exception as e:
                    self.error = e
                    logging.error(f"Analysis failed: {str(e)}")
                    self.parent.run_in_main_thread(self.show_error)
                finally:
                    self.parent.run_in_main_thread(self.hide_progress)
        
        # Create and start worker
        worker = AnalysisWorker(self, file_paths)
        threading.Thread(target=worker.run, daemon=True).start()

    def load_and_convert(self):
        def worker():
            try:
                input_format = self.input_format.get()
                output_format = self.output_format.get()
                
                # Get selected files
                selections = self.input_listbox.curselection()
                if not selections:
                    self.run_in_main_thread(messagebox.showerror, "Error", "No files selected")
                    return
                
                # Get file paths
                file_paths = [self.input_listbox.get(idx).split(' [')[0] for idx in selections]
                
                # Analyze timestamps before loading
                self.run_in_main_thread(lambda: self.progress_bar.pack())
                self.run_in_main_thread(lambda: self.progress_var.set(10))
                
                # Analyze timestamps
                summary = self.analyze_selected_files_timestamps(file_paths, input_format)
                
                # Show timestamp analysis popup
                self.run_in_main_thread(lambda: self.show_timestamp_analysis_popup(summary))
                
                self.run_in_main_thread(lambda: self.progress_var.set(30))
                
                # Continue with existing loading process
                dfs = []
                for idx, file_path in enumerate(file_paths):
                    df = self.loader.load_data([file_path], input_format)[0]
                    if df is not None:
                        dfs.append(df)
                    progress = 30 + (40 * (idx + 1) / len(file_paths))
                    self.run_in_main_thread(lambda *a, **k: self.progress_var.set(progress))
                
                if not dfs:
                    print("Error: No valid data loaded from file(s)")
                    self.run_in_main_thread(messagebox.showerror, "Error", "No valid data loaded")
                    self.run_in_main_thread(lambda: self.progress_bar.pack_forget())
                    return
                
                # Combine all dataframes
                data = pd.concat(dfs, ignore_index=True)
                
                # Get date range from user
                start_date = self.start_date_entry.get()
                end_date = self.end_date_entry.get()
                
                if start_date and end_date:
                    try:
                        data = self.loader.filter_data_by_date_range(data, start_date, end_date)
                    except Exception as e:
                        self.run_in_main_thread(messagebox.showerror, "Error", f"Date filtering failed: {str(e)}")
                        self.run_in_main_thread(lambda: self.progress_bar.pack_forget())
                        return
                
                self.run_in_main_thread(lambda: self.progress_var.set(80))
                
                # Get balancing parameters and continue with existing process
                try:
                    target_records = int(self.target_records_entry.get()) if self.target_records_entry.get() else None
                    min_records = int(self.min_records_entry.get()) if self.min_records_entry.get() else None
                except ValueError:
                    target_records = None
                    min_records = None
                
                # Balance the data
                try:
                    data = self.loader.balance_ticker_data(data, target_records, min_records)
                except Exception as e:
                    self.run_in_main_thread(messagebox.showerror, "Error", f"Data balancing failed: {str(e)}")
                    self.run_in_main_thread(lambda: self.progress_bar.pack_forget())
                    return
                
                self.run_in_main_thread(lambda: self.progress_var.set(90))
                
                # Continue with existing save process...
                
            except Exception as e:
                logging.error(f"Data processing failed: {str(e)}")
                self.run_in_main_thread(messagebox.showerror, "Error", f"Processing failed: {str(e)}")
            finally:
                self.run_in_main_thread(lambda: self.progress_bar.pack_forget())
        
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
                self.refresh_data()
                break

    def refresh_file_list(self):
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

    def view_selected_file(self):
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No file selected")
            return
        file_path = self.file_listbox.get(selection[0])
        print("Viewing file:", file_path)
        # Remove [type] if present
        file_path = file_path.split(' [')[0]
        ext = os.path.splitext(file_path)[1].lower()
        fmt = DataLoader.EXT_TO_FORMAT.get(ext, None)
        def worker():
            try:
                if fmt == 'keras':
                    try:
                        model = DataLoader.load_file_by_type(file_path, fmt)
                        import io
                        stream = io.StringIO()
                        model.summary(print_fn=lambda x: stream.write(x + '\n'))
                        summary_str = stream.getvalue()
                        def show_keras():
                            popup = tk.Toplevel(self.root)
                            popup.title("Keras Model Summary")
                            text = tk.Text(popup, wrap='word')
                            text.insert('1.0', summary_str)
                            text.pack(fill='both', expand=True)
                        self.run_in_main_thread(show_keras)
                        return
                    except Exception as e:
                        self.run_in_main_thread(lambda: messagebox.showerror("Error", f"Failed to load Keras model: {str(e)}"))
                        return
                df = DataLoader.load_file_by_type(file_path, fmt)
                print("DF columns:", df.columns)
                print(df.head())
                def update_table():
                    self.data_tree.delete(*self.data_tree.get_children())
                    cols = list(df.columns)
                    self.data_tree['columns'] = cols
                    self.data_tree['show'] = 'headings'
                    for col in cols:
                        self.data_tree.heading(col, text=col)
                        self.data_tree.column(col, width=100, stretch=True, anchor='center')
                    max_rows = 1000
                    for i, (_, row) in enumerate(df.iterrows()):
                        if i >= max_rows:
                            break
                        self.data_tree.insert('', 'end', values=tuple(row))
                self.run_in_main_thread(update_table)
            except Exception as e:
                print("Failed to read file:", file_path)
                logging.exception(f"Failed to preview file: {file_path}")
                self.run_in_main_thread(lambda: messagebox.showerror("Error", f"Failed to read file: {str(e)}"))
        threading.Thread(target=worker, daemon=True).start()

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
        try:
            # If a file is selected in the file_listbox, show its data
            selection = self.file_listbox.curselection()
            if selection:
                file_path = self.file_listbox.get(selection[0])
                file_path = file_path.split(' [')[0]
                ext = os.path.splitext(file_path)[1].lower()
                fmt = DataLoader.EXT_TO_FORMAT.get(ext, None)
                try:
                    if fmt == 'keras':
                        # Show model summary in popup, skip table
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
                    df = DataLoader.load_file_by_type(file_path, fmt)
                    self.data_tree.delete(*self.data_tree.get_children())
                    cols = list(df.columns)
                    self.data_tree['columns'] = cols
                    self.data_tree['show'] = 'headings'
                    for col in cols:
                        self.data_tree.heading(col, text=col)
                        self.data_tree.column(col, width=100, stretch=True, anchor='center')
                    for _, row in df.iterrows():
                        self.data_tree.insert('', 'end', values=tuple(row))
                    for col in cols:
                        self.data_tree.column(col, width=tkFont.Font().measure(col) + 20)
                    if not hasattr(self, 'yscroll'):
                        self.yscroll = ttk.Scrollbar(self.data_tree.master, orient='vertical', command=self.data_tree.yview)
                        self.data_tree.configure(yscrollcommand=self.yscroll.set)
                        self.yscroll.pack(side='right', fill='y')
                    print("\n=== Data Table Screenshot ===")
                    print(df.head(10).to_string(index=False))
                    print("============================\n")
                    return
                except Exception as e:
                    logging.exception(f"Refresh data failed for selected file: {str(e)}")
                    print(f"Refresh data failed for selected file: {str(e)}")
                    messagebox.showerror("Error", f"Refresh data failed for selected file: {str(e)}")
                    return
            # Otherwise, fall back to showing tickers_data from DuckDB
            for item in self.data_tree.get_children():
                self.data_tree.delete(item)
            data = self.connector.read_shared_data('tickers_data', 'pandas')
            screenshot_cols = ['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'vol', 'openint', 'format']
            screenshot_cols = [col for col in screenshot_cols if col in data.columns]
            self.data_tree['columns'] = screenshot_cols
            self.data_tree['show'] = 'headings'
            for col in screenshot_cols:
                self.data_tree.heading(col, text=col)
                self.data_tree.column(col, width=100, stretch=True, anchor='center')
            for _, row in data.iterrows():
                self.data_tree.insert('', 'end', values=tuple(row[col] for col in screenshot_cols))
            for col in screenshot_cols:
                self.data_tree.column(col, width=tkFont.Font().measure(col) + 20)
            if not hasattr(self, 'yscroll'):
                self.yscroll = ttk.Scrollbar(self.data_tree.master, orient='vertical', command=self.data_tree.yview)
                self.data_tree.configure(yscrollcommand=self.yscroll.set)
                self.yscroll.pack(side='right', fill='y')
            print("\n=== Data Table Screenshot ===")
            print(data[screenshot_cols].head(10).to_string(index=False))
            print("============================\n")
        except Exception as e:
            logging.exception(f"Refresh data failed: {str(e)}")
            print(f"Refresh data failed: {str(e)}")
            messagebox.showerror("Error", f"Refresh data failed: {str(e)}")

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
                self.run_in_main_thread(messagebox.showerror, "Error", "No file(s) selected to remove")
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
            self.run_in_main_thread(update_gui)
        threading.Thread(target=worker, daemon=True).start()

    def run_in_main_thread(self, func):
        """Safely run a function in the main thread"""
        self.root.after(0, func)

    def show_loader_manual(self):
        guide = (
            """
DATA LOADER TAB - USER MANUAL\n\n
1. Browse Files: Click to select one or more data files (CSV, TXT, JSON, DuckDB, etc.). Selected files appear in the list.\n\n
2. Preview File: Select a file from the list and click to view its contents before processing.\n\n
3. Date Range Selection: Enter start and end dates (YYYY-MM-DD) to filter data by time period.\n\n
4. Data Balancing Options:
   - Target Records: Desired number of records per ticker
   - Minimum Records: Minimum required records for a ticker to be included
   - Leave blank for automatic values based on data distribution\n\n
5. Input/Output Format: Choose the input format (matches your files) and desired output format for conversion.\n\n
6. Merge/Consolidate Files: Click to merge selected files, apply date filtering and balancing, and save as a single file.\n\n
7. Progress Bar: Shows progress during batch operations.\n\n
Tip: Use Preview to check file structure before processing.\n
"""
        )

        popup = tk.Toplevel(self.root)
        popup.title("Data Loader Manual")
        popup.geometry("600x800")
        
        # Create a frame with scrollbar
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
DATA VIEW TAB - USER MANUAL

1. Data Navigation
-----------------
• Available Data Files: Lists all supported files in data directory
• Multiple selection enabled for batch operations
• File list shows format for each file
• Hierarchical view of data directory structure

2. Viewing Options
-----------------
• View File: Display selected file's contents in data table
• Data table shows:
  - Ticker symbols
  - Timestamps
  - OHLCV data (Open, High, Low, Close, Volume)
  - Additional fields if present
• Sortable columns for easy analysis
• Horizontal and vertical scrolling for large datasets

3. Data Analysis Features
------------------------
• Statistics Display:
  - Records per ticker
  - Date range coverage
  - Data distribution
  - Missing value counts
• Data Quality Indicators:
  - Highlights gaps in time series
  - Shows data completeness
  - Identifies potential anomalies

4. Data Management
-----------------
• Remove File: Delete selected files from disk
• Refresh Data: Update file list and table view
• Export Options: Save viewed data in various formats
• Batch Operations: Process multiple files together

5. Display Settings
------------------
• Adjustable column widths
• Sortable by any column
• Customizable date/time formats
• Numeric precision control

6. Performance Features
----------------------
• Efficient loading of large datasets
• Pagination for better performance
• Memory-optimized data handling
• Quick search and filter capabilities

Tips for Effective Use:
----------------------
1. Regular refresh keeps view current
2. Sort by date to check continuity
3. Use filters to focus on specific data
4. Check statistics for data quality
5. Export filtered views as needed

Troubleshooting:
---------------
• Slow loading: Try reducing view range
• Missing data: Check file permissions
• Format issues: Verify file type
• Display problems: Refresh view

Data Quality Checks:
------------------
• Verify timestamp continuity
• Check for price anomalies
• Monitor volume consistency
• Validate ticker symbols
"""

        popup = tk.Toplevel(self.root)
        popup.title("Data View Manual")
        popup.geometry("600x800")
        
        # Create a frame with scrollbar
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

    def show_stooq_analysis_popup(self, analysis):
        """Display analysis results in a popup window"""
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
        summary_scroll = ttk.Scrollbar(summary_frame, orient='vertical', 
                                     command=summary_text.yview)
        summary_text.configure(yscrollcommand=summary_scroll.set)
        
        summary_text.pack(side='left', fill='both', expand=True)
        summary_scroll.pack(side='right', fill='y')
        
        # Details tab
        details_frame = ttk.Frame(notebook)
        notebook.add(details_frame, text='Details')
        
        details_text = tk.Text(details_frame, wrap='word', padx=10, pady=10)
        details_scroll = ttk.Scrollbar(details_frame, orient='vertical', 
                                     command=details_text.yview)
        details_text.configure(yscrollcommand=details_scroll.set)
        
        details_text.pack(side='left', fill='both', expand=True)
        details_scroll.pack(side='right', fill='y')
        
        # Format and insert the content
        try:
            summary_content = self.format_analysis_summary(analysis)
            details_content = self.format_analysis_details(analysis)
            
            summary_text.insert('1.0', summary_content)
            details_text.insert('1.0', details_content)
            
            summary_text.config(state='disabled')
            details_text.config(state='disabled')
            
        except Exception as format_error:
            logging.error(f"Error formatting analysis: {str(format_error)}")
            summary_text.insert('1.0', f"Error formatting analysis: {str(format_error)}")
            summary_text.config(state='disabled')
        
        # Add control buttons
        button_frame = ttk.Frame(popup)
        button_frame.pack(fill='x', pady=10)
        
        ttk.Button(button_frame, text="Export", 
                   command=lambda: self.export_analysis(analysis)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Close", 
                   command=popup.destroy).pack(side='right', padx=5)

    def format_analysis_summary(self, analysis):
        """Format summary of analysis data"""
        summary = f"""STOOQ DATA ANALYSIS SUMMARY
{'='*50}

OVERALL STATISTICS
-----------------
Total Files: {analysis['summary']['total_files']}
Total Records: {analysis['summary']['total_records']:,}
Total Unique Tickers: {analysis['summary']['total_tickers']}

DATE RANGE
----------
Earliest Date: {analysis['summary']['earliest_date'].strftime('%Y-%m-%d')}
Latest Date: {analysis['summary']['latest_date'].strftime('%Y-%m-%d')}
Total Trading Days: {(analysis['summary']['latest_date'] - analysis['summary']['earliest_date']).days + 1}

RECOMMENDATIONS
--------------
• Suggested date range for analysis:
  Start: {analysis['summary']['earliest_date'].strftime('%Y-%m-%d')}
  End: {analysis['summary']['latest_date'].strftime('%Y-%m-%d')}

• Suggested record counts:
  Target: {analysis['summary']['total_records'] // analysis['summary']['total_tickers']:,}
  Minimum: {(analysis['summary']['total_records'] // analysis['summary']['total_tickers']) // 2:,}
"""
        return summary

    def format_analysis_details(self, analysis):
        """Format detailed analysis data"""
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

    def export_analysis(self, analysis):
        """Export analysis to a file"""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
                title="Export Analysis Report"
            )
            if file_path:
                with open(file_path, 'w') as f:
                    f.write(self.format_analysis_summary(analysis))
                    f.write("\n\n")
                    f.write(self.format_analysis_details(analysis))
                messagebox.showinfo("Success", "Analysis exported successfully")
        except Exception as e:
            logging.error(f"Error exporting analysis: {str(e)}")
            messagebox.showerror("Error", f"Failed to export analysis: {str(e)}")

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