FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python
RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-tk \
    build-essential \
    curl \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages using system pip with --break-system-packages
RUN python3 -m pip install \
    pandas \
    numpy \
    sqlalchemy \
    duckdb \
    configparser \
    pyarrow \
    polars \
    tensorflow \
    scikit-learn \
    --break-system-packages

# Set memory optimization environment variables
ENV PYTHONUNBUFFERED=1
ENV DUCKDB_MEMORY_LIMIT=4GB
ENV PANDAS_CHUNKSIZE=10000

# Set working directory
WORKDIR /app

# Copy ALL required application files (refactored modules)
COPY lazy_loader.py data_loader.py data_sources.py data_adapter.py file_operations.py progress_tracker.py gui_components.py gui_main.py gui_grid_layout.py user_manual.py main_refactored.py data_config.ini ./

# Default command to run the refactored module
CMD ["python3", "main_refactored.py"]

