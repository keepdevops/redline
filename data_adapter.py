#!/usr/bin/env python3
"""
Data adapter for machine learning and reinforcement learning data preparation.
"""

import logging
import pandas as pd
import polars as pl
import pyarrow as pa
import numpy as np
import tensorflow as tf
from typing import Union, List, Dict


class DataAdapter:
    """Adapter for preparing data for machine learning models"""
    
    def __init__(self):
        """Initialize data adapter"""
        pass
    
    def prepare_training_data(self, data: Union[List[pd.DataFrame], List[pl.DataFrame], List[pa.Table]], 
                             format: str) -> Union[List[np.ndarray], tf.data.Dataset]:
        """
        Prepare training data for machine learning models.
        
        Args:
            data: List of dataframes to prepare
            format: Target format ('numpy' or 'tensorflow')
            
        Returns:
            Prepared data in specified format
        """
        try:
            if isinstance(data, list) and data:
                if format == 'numpy':
                    return [d.to_numpy() for d in data if isinstance(d, (pd.DataFrame, pl.DataFrame))]
                elif format == 'tensorflow':
                    numpy_arrays = [d.to_numpy() for d in data if isinstance(d, (pd.DataFrame, pl.DataFrame))]
                    return tf.data.Dataset.from_tensor_slices(numpy_arrays)
            return []
        except Exception as e:
            logging.error(f"Failed to prepare training data: {str(e)}")
            raise

    def prepare_rl_state(self, data: Union[pd.DataFrame, pl.DataFrame, pa.Table], 
                        portfolio: Dict, format: str) -> Union[np.ndarray, tf.Tensor]:
        """
        Prepare reinforcement learning state data.
        
        Args:
            data: Input data
            portfolio: Portfolio information
            format: Target format ('numpy' or 'tensorflow')
            
        Returns:
            Prepared state data
        """
        try:
            if isinstance(data, (pl.DataFrame, pa.Table)):
                data = data.to_pandas()
            
            # Extract price data for RL state
            state = data[['close']].to_numpy()
            
            if format == 'tensorflow':
                return tf.convert_to_tensor(state, dtype=tf.float32)
            return state
        except Exception as e:
            logging.error(f"Failed to prepare RL state: {str(e)}")
            raise

    def summarize_preprocessed(self, data: Union[List[np.ndarray], tf.data.Dataset], 
                              format: str) -> Dict:
        """
        Summarize preprocessed data.
        
        Args:
            data: Preprocessed data
            format: Data format
            
        Returns:
            Summary dictionary
        """
        try:
            if isinstance(data, list):
                return {
                    'format': format, 
                    'size': len(data),
                    'type': 'numpy_arrays'
                }
            elif isinstance(data, tf.data.Dataset):
                return {
                    'format': format,
                    'type': 'tensorflow_dataset',
                    'cardinality': data.cardinality().numpy() if data.cardinality().numpy() >= 0 else 'unknown'
                }
            else:
                return {
                    'format': format,
                    'type': 'unknown',
                    'size': 0
                }
        except Exception as e:
            logging.error(f"Failed to summarize preprocessed data: {str(e)}")
            raise

    def normalize_data(self, data: Union[pd.DataFrame, np.ndarray], 
                      method: str = 'minmax') -> Union[pd.DataFrame, np.ndarray]:
        """
        Normalize data for machine learning.
        
        Args:
            data: Input data to normalize
            method: Normalization method ('minmax', 'standard', 'robust')
            
        Returns:
            Normalized data
        """
        try:
            from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
            
            if method == 'minmax':
                scaler = MinMaxScaler()
            elif method == 'standard':
                scaler = StandardScaler()
            elif method == 'robust':
                scaler = RobustScaler()
            else:
                raise ValueError(f"Unknown normalization method: {method}")
            
            if isinstance(data, pd.DataFrame):
                # Normalize numeric columns only
                numeric_cols = data.select_dtypes(include=[np.number]).columns
                data_normalized = data.copy()
                data_normalized[numeric_cols] = scaler.fit_transform(data[numeric_cols])
                return data_normalized
            else:
                return scaler.fit_transform(data)
                
        except Exception as e:
            logging.error(f"Failed to normalize data: {str(e)}")
            raise

    def create_sequences(self, data: np.ndarray, sequence_length: int = 60, 
                        target_col: int = 0) -> tuple:
        """
        Create sequences for time series prediction.
        
        Args:
            data: Input time series data
            sequence_length: Length of sequences to create
            target_col: Column index for target values
            
        Returns:
            Tuple of (X, y) sequences
        """
        try:
            X, y = [], []
            
            for i in range(sequence_length, len(data)):
                X.append(data[i-sequence_length:i])
                y.append(data[i, target_col])
            
            return np.array(X), np.array(y)
            
        except Exception as e:
            logging.error(f"Failed to create sequences: {str(e)}")
            raise

    def calculate_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators for financial data.
        
        Args:
            data: Financial data with OHLCV columns
            
        Returns:
            Data with technical indicators added
        """
        try:
            df = data.copy()
            
            # Simple Moving Averages
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            
            # Exponential Moving Averages
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            
            # MACD
            df['macd'] = df['ema_12'] - df['ema_26']
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            bb_std = df['close'].rolling(window=20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            
            return df
            
        except Exception as e:
            logging.error(f"Failed to calculate technical indicators: {str(e)}")
            raise
