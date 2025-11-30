@echo off
REM Build script for Windows
REM Run this on a Windows machine with Python 3.10+ installed

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
pyinstaller --onefile --windowed --name "MartinezOrders" --icon=icon.ico --add-data "config.json;." phonecaller.py

echo.
echo Done! Executable is in dist\MartinezOrders.exe
echo.
echo NOTE: Copy config.json to the same folder as MartinezOrders.exe
pause
