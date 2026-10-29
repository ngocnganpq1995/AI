@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo ========================================
echo       STOCK NEWS AI DASHBOARD V4
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo Chua tim thay Python.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tao moi truong Python...
    py -m venv .venv
)

echo [2/3] Cai/cap nhat thu vien...
call ".venv\Scripts\activate.bat"
python -m pip install -r "requirements.txt"

if errorlevel 1 (
    echo Cai thu vien that bai.
    pause
    exit /b 1
)

echo [3/3] Mo dashboard V4...
python -m streamlit run "app.py"
pause
