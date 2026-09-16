@echo off
REM ============================================================
REM  Build GuitarTabEditor.exe  (no console window, custom icon)
REM  Run this file from the folder that contains guitar_tab_app.py
REM ============================================================

REM 1) Install PyInstaller once (safe to re-run):
python -m pip install --upgrade pyinstaller

REM 2) Build a single windowed .exe with our icon.
REM    --noconsole  = no black cmd window
REM    --icon       = the .exe file's icon
REM    --add-data   = bundle the .ico/.png so the window can load them at runtime
python -m PyInstaller --onefile --noconsole ^
  --name "GuitarTabEditor" ^
  --icon "guitar_tab.ico" ^
  --add-data "guitar_tab.ico;." ^
  --add-data "guitar_tab.png;." ^
  guitar_tab_app.py

echo.
echo ============================================================
echo  Done! Your app is here:  dist\GuitarTabEditor.exe
echo  Double-click it - no cmd window, guitar icon everywhere.
echo ============================================================
pause
