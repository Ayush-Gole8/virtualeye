@echo off
REM Virtual Eye 3.0 - Quick Start Script for Windows

echo.
echo ========================================
echo Virtual Eye 3.0 - Quick Start
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please download from: https://nodejs.org/
    pause
    exit /b 1
)

echo [OK] Python and Node.js found
echo.

REM Create backend virtual environment
echo [1/5] Setting up Python backend...
cd backend
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

REM Install backend dependencies
echo [2/5] Installing Python dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

REM Start backend in new window
echo [3/5] Starting Flask backend server...
start cmd /k "cd backend && venv\Scripts\activate.bat && python server.py"

REM Wait for backend to start
timeout /t 5 /nobreak

REM Go back to root
cd ..

REM Install frontend dependencies
echo [4/5] Installing Node.js dependencies...
call npm install --silent
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install Node.js dependencies
    pause
    exit /b 1
)

REM Start frontend
echo [5/5] Starting React frontend server...
echo.
echo ========================================
echo Virtual Eye 3.0 is starting!
echo ========================================
echo.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:5000
echo.
echo Backend window should open separately.
echo If not, open new terminal and run: cd backend && venv\Scripts\activate.bat && python server.py
echo.
echo Press Ctrl+C in this window to stop the frontend.
echo.
call npm run dev

pause
