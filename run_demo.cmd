@echo off
cd /d "%~dp0"
python -c "import PIL" 2>nul
if errorlevel 1 (
    python -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)
python run_demo.py %*
exit /b %errorlevel%
