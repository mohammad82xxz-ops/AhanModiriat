@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo ERROR: Python 3.10+ not found.& pause & exit /b 1)
python -m py_compile app.py test_smoke.py
if errorlevel 1 (pause & exit /b 1)
python test_smoke.py
if errorlevel 1 (pause & exit /b 1)
python -m pip install --upgrade pyinstaller
if errorlevel 1 (pause & exit /b 1)
if exist build rmdir /s /q build
if exist dist\AhanModiriat rmdir /s /q dist\AhanModiriat
python -m PyInstaller --clean --noconfirm AhanModiriat.spec
if errorlevel 1 (pause & exit /b 1)
if not exist dist\AhanModiriat\AhanModiriat.exe (echo ERROR: EXE missing.& pause & exit /b 1)
echo SUCCESS: dist\AhanModiriat\AhanModiriat.exe
echo Keep the complete dist\AhanModiriat folder and back up data\business.db.
pause
