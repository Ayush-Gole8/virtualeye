#!/bin/bash

# Virtual Eye 3.0 - Quick Start Script for Linux/macOS

echo ""
echo "========================================"
echo "Virtual Eye 3.0 - Quick Start"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install from: https://www.python.org/downloads/"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed"
    echo "Please install from: https://nodejs.org/"
    exit 1
fi

echo "[OK] Python and Node.js found"
echo ""

# Create backend virtual environment
echo "[1/5] Setting up Python backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install backend dependencies
echo "[2/5] Installing Python dependencies..."
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Python dependencies"
    exit 1
fi

# Start backend in background
echo "[3/5] Starting Flask backend server..."
python server.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 5

# Go back to root
cd ..

# Install frontend dependencies
echo "[4/5] Installing Node.js dependencies..."
npm install --silent
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Node.js dependencies"
    kill $BACKEND_PID
    exit 1
fi

# Start frontend
echo "[5/5] Starting React frontend server..."
echo ""
echo "========================================"
echo "Virtual Eye 3.0 is starting!"
echo "========================================"
echo ""
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:5000"
echo ""
echo "Backend is running in the background."
echo ""
echo "Press Ctrl+C to stop both servers."
echo ""

npm run dev

# Cleanup
echo ""
echo "Stopping backend..."
kill $BACKEND_PID
