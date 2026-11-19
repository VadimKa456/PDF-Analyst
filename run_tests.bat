@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\backend"

if not exist "..\.venv\Scripts\python.exe" (
  echo [setup] Python environment not found. Running setup.bat...
  call ..\setup.bat
  if errorlevel 1 exit /b 1
)

echo Running pytest...
"..\.venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 (
  echo.
  echo Tests failed.
  exit /b 1
)

echo.
echo Tests passed.
echo.
echo To run the end-to-end test, start start.bat in another window, then run:
echo   cd backend
echo   python _final_e2e.py
exit /b 0
