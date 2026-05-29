@echo off
setlocal
echo ================================================
echo  KeyWise AI — Build Script
echo ================================================
echo.

:: Step 1: Install dependencies
echo [1/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (echo ERROR: pip install failed & pause & exit /b 1)

:: Step 2: Generate icon
echo.
echo [2/4] Generating icon...
python generate_icon.py
if errorlevel 1 (echo WARNING: Icon generation failed, using default.)

:: Step 3: Install PyInstaller
echo.
echo [3/4] Installing PyInstaller...
pip install pyinstaller

:: Step 4: Build .exe
echo.
echo [4/4] Building KeyWiseAI.exe ...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name "KeyWiseAI" ^
    --icon "assets\icon.ico" ^
    --add-data "assets;assets" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "PIL._tkinter_finder" ^
    main.py

echo.
if exist "dist\KeyWiseAI.exe" (
    echo ================================================
    echo  SUCCESS! Find your app at: dist\KeyWiseAI.exe
    echo  Share this .exe — no Python needed on target PC.
    echo ================================================
) else (
    echo ERROR: Build failed. Check output above.
)
pause
