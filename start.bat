@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Python environment not found. Running setup.bat...
  call setup.bat
  if errorlevel 1 exit /b 1
)

if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul

if not exist "frontend\dist\index.html" (
  echo [WARN] frontend\dist\index.html is missing.
  echo        The API will work, but the UI will not be available.
  echo        Run setup.bat to build the frontend.
  echo.
)

echo ============================================
echo  PDF Analyst
echo  http://127.0.0.1:8000
echo  Press Ctrl+C to stop the server.
echo ============================================
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000/'"

cd backend
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Server stopped.
exit /b 0
