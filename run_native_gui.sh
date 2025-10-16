#!/bin/bash

echo "🚀 Starting REDLINE Native GUI..."
echo "=================================="

# Check if virtual environment exists
if [ ! -d "redline_env" ]; then
    echo "❌ Virtual environment not found. Please run the setup first."
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source redline_env/bin/activate

# Check if tkinter is available
echo "🔍 Checking tkinter availability..."
python -c "import tkinter; print('✅ tkinter available')" 2>/dev/null || {
    echo "❌ tkinter not available in virtual environment"
    echo "💡 Trying system Python instead..."
    
    # Try system Python
    /usr/bin/python3 -c "import tkinter; print('✅ tkinter available in system Python')" 2>/dev/null || {
        echo "❌ tkinter not available in system Python either"
        echo "💡 Falling back to web GUI..."
        echo "🌐 Starting web GUI at http://localhost:8080"
        python3 web_gui.py &
        open http://localhost:8080
        exit 0
    }
    
    # Use system Python with virtual environment packages
    echo "🔄 Using system Python with virtual environment packages..."
    export PYTHONPATH="$(pwd)/redline_env/lib/python3.13/site-packages:$PYTHONPATH"
    /usr/bin/python3 main.py
    exit $?
}

# Use virtual environment Python
echo "🎯 Using virtual environment Python..."
python main.py
