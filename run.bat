@echo off
:: KeyWise AI — Easy launcher
:: Uses Python 3.12 (the correct installation)

set PYTHON=C:\Users\DELL\AppData\Local\Programs\Python\Python312\python.exe

:: Check if packages are installed; if not, install them first
%PYTHON% -c "import groq" 2>nul
if errorlevel 1 (
    echo [KeyWise] Installing required packages...
    %PYTHON% -m pip install groq keyboard pystray Pillow pyperclip pywin32
    echo.
)

:: Run the app
echo [KeyWise] Starting...
%PYTHON% main.py
