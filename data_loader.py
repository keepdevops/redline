#!/usr/bin/env python3
"""
Core DataLoader class for handling file loading and data standardization.
"""

import os
import logging
import configparser
import pandas as pd
from typing import Union, List, Dict


class DataLoader:
    """Core data loader for handling various file formats and standardization"""
    
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

    def __init__(self, config_path: str = 'data_config.ini'):
        """Initialize DataLoader with configuration"""
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.db_path = self.config['Data'].get('db_path', '/app/redline_data.duckdb')
        self.csv_dir = self.config['Data'].get('csv_dir', '/app/data')
        self.json_dir = self.config['Data'].get('json_dir', '/app/data/json')
        self.parquet_dir = self.config['Data'].get('parquet_dir', '/app/data/parquet')

    @staticmethod
    def clean_and_select_columns(data: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize DataFrame columns"""
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

    def validate_data(self, file_path: str, format: str) -> bool:
        """Validate data file format"""
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

    def _standardize_txt_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize Stooq TXT format columns"""
        try:
            print('Original columns:', list(df.columns))
            
            # Remove BOM and strip whitespace from column names
            df.columns = [c.lstrip('\ufeff').strip() for c in df.columns]
            
            # Map Stooq-specific headers to standard schema
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
            
            # Rename columns
            df = df.rename(columns=col_map)
            
            # Combine DATE and TIME into timestamp
            if 'date' in df.columns and 'time' in df.columns:
                # Convert date and time to timestamp
                df['timestamp'] = pd.to_datetime(
                    df['date'].astype(str) + df['time'].astype(str).str.zfill(6),
                    format='%Y%m%d%H%M%S',
                    errors='coerce'
                )
                # Drop original date and time columns
                df = df.drop(['date', 'time'], axis=1)
            
            # Ensure all required columns exist
            for col in self.SCHEMA:
                if col not in df.columns:
                    df[col] = None
            
            # Select only schema columns
            df = df[self.SCHEMA]
            
            # Drop rows with missing critical data
            df = df.dropna(subset=['timestamp', 'close'])
            
            return df
            
        except Exception as e:
            logging.error(f"Error standardizing TXT columns: {str(e)}")
            raise

    def load_file_by_type(self, file_path: str, filetype: str = None) -> pd.DataFrame:
        """Load a single file by type"""
        import duckdb
        
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
            # Standardize Stooq format
            df = self._standardize_txt_columns(df)
            return df
        elif filetype == 'parquet':
            return pd.read_parquet(file_path)
        elif filetype == 'feather':
            return pd.read_feather(file_path)
        elif filetype == 'duckdb':
            conn = duckdb.connect(file_path)
            df = conn.execute("SELECT * FROM tickers_data").fetchdf()
            conn.close()
            return df
        else:
            raise ValueError(f"Unsupported file type: {filetype}")

    def load_data(self, file_paths: List[str], format: str) -> List[pd.DataFrame]:
        """Load multiple files"""
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
                if format == 'txt':
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

    @staticmethod
    def save_file_by_type(data: Union[pd.DataFrame, List], file_path: str, format: str):
        """Save data to file in specified format"""
        if isinstance(data, list):
            data = pd.concat(data, ignore_index=True)
        
        if format == 'csv':
            data.to_csv(file_path, index=False)
        elif format == 'json':
            data.to_json(file_path, orient='records', lines=True)
        elif format == 'parquet':
            data.to_parquet(file_path, index=False)
        elif format == 'feather':
            data.to_feather(file_path)
        elif format == 'duckdb':
            import duckdb
            conn = duckdb.connect(file_path)
            conn.execute("DROP TABLE IF EXISTS tickers_data")
            conn.execute("CREATE TABLE tickers_data AS SELECT * FROM data")
            conn.close()
        else:
            raise ValueError(f"Unsupported output format: {format}")
