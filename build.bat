@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo       AhanModiriat - Windows Builder
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found. Install Python 3.13 and enable Add Python to PATH.
  pause
  exit /b 1
)

if not exist "AhanModiriatBuildKit\app.py" (
  echo ERROR: AhanModiriatBuildKit\app.py was not found.
  echo Run this file from the project root folder.
  pause
  exit /b 1
)

echo [1/4] Checking Python syntax...
python -m py_compile "AhanModiriatBuildKit\app.py"
if errorlevel 1 goto :failed

echo [2/4] Running regression tests...
python -m unittest discover -s "AhanModiriatBuildKit" -p "test_app.py"
if errorlevel 1 goto :failed

echo [3/4] Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :failed

echo [4/4] Building EXE...
if exist "build" rmdir /s /q "build"
if exist "dist\AhanModiriat.exe" del /q "dist\AhanModiriat.exe"
python -m PyInstaller --clean --noconfirm --onefile --console --name AhanModiriat "AhanModiriatBuildKit\app.py"
if errorlevel 1 goto :failed

if not exist "dist\AhanModiriat.exe" (
  echo ERROR: The EXE was not created.
  goto :failed
)

if not exist "dist\data" mkdir "dist\data"
echo.
echo SUCCESS: dist\AhanModiriat.exe
echo Database folder: dist\data
echo Keep the data folder when moving/updating the application.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read the error messages above.
pause
exit /b 1
