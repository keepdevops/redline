#!/bin/bash

# REDLINE GUI Docker Runner for macOS
# This script sets up X11 forwarding to run the GUI from within Docker

echo "Setting up X11 forwarding for REDLINE GUI..."

# Start XQuartz if not running
if ! pgrep -x "XQuartz" > /dev/null; then
    echo "Starting XQuartz..."
    open -a XQuartz
    sleep 10  # Wait for XQuartz to start
fi

# Set local DISPLAY and allow connections
export DISPLAY=:1
echo "Allowing X11 connections..."
xhost +localhost || echo "Warning: xhost +localhost failed"

# Ensure .Xauthority has Docker entry
if ! xauth list | grep -q "localhost:1"; then
    echo "Adding Xauth cookie for Docker host..."
    xauth add localhost:1 . 958e725fb0d7e7d91c328a163247a41b
fi

# Check if we're on ARM or Intel Mac
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    DOCKER_IMAGE="redline_arm"
    echo "Running on Apple Silicon (ARM64)"
else
    DOCKER_IMAGE="redline_x86"
    echo "Running on Intel Mac (x86_64)"
fi

echo "Starting REDLINE container with GUI support..."

# Run Docker container with X11 forwarding
docker run -it --rm --network host \
    -e DISPLAY=localhost:1 \
    -v $HOME/.Xauthority:/root/.Xauthority:ro \
    -v $(pwd)/data:/app/data \
    -v $(pwd):/app/host \
    --name redline_gui \
    $DOCKER_IMAGE \
    python3 /app/host/data_module_shared.py --task gui

echo "REDLINE GUI session ended."#!/bin/bash

# REDLINE GUI Docker Runner for macOS
# This script sets up X11 forwarding to run the GUI from within Docker

echo "Setting up X11 forwarding for REDLINE GUI..."

# Get local IP address (for reference)
LOCAL_IP=$(ifconfig en0 | grep inet | grep -v inet6 | awk '{print $2}')
echo "Local IP: $LOCAL_IP"

# Start XQuartz if not running
if ! pgrep -x "XQuartz" > /dev/null; then
    echo "Starting XQuartz..."
    open -a XQuartz
    sleep 5  # Wait for XQuartz to start
fi

# Set display to the working one (e.g., localhost:0 or :0 based on xeyes test)
export DISPLAY=localhost:0  # Change to :0 or 192.168.50.33:0 if that worked
echo "DISPLAY set to: $DISPLAY"

# Allow connections (try local first)
xhost +local: || echo "Warning: xhost +local: failed"
xhost +$LOCAL_IP || echo "Warning: xhost +$LOCAL_IP failed"

# Add xauth entry if needed
xauth add $DISPLAY . $(openssl rand -hex 16 2>/dev/null || echo "f8c37ea64e4472075d27d39caa0f2186")

# Check if we're on ARM or Intel Mac
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    DOCKER_IMAGE="redline_arm"
    echo "Running on Apple Silicon (ARM64)"
else
    DOCKER_IMAGE="redline_x86"
    echo "Running on Intel Mac (x86_64)"
fi

echo "Starting REDLINE container with GUI support..."

# Run Docker container with X11 forwarding
docker run -it --rm \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v $HOME/.Xauthority:/root/.Xauthority:ro \
    -v $(pwd)/data:/app/data \
    -v $(pwd):/app/host \
    --name redline_gui \
    $DOCKER_IMAGE \
    python3 /app/host/data_module_shared.py --task gui

echo "REDLINE GUI session ended."
