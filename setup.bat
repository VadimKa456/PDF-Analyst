@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  PDF Analyst - setup
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.11+ and add it to PATH.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [1/4] Virtual environment already exists.
)

echo [2/4] Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto :fail

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo [3/4] Created .env from .env.example
  )
) else (
  echo [3/4] .env already exists - kept unchanged.
)

set "NPM_CMD="
call :find_npm
if defined NPM_CMD (
  echo [4/4] Building frontend...
  pushd frontend
  call "%NPM_CMD%" ci
  if errorlevel 1 (
    popd
    echo [WARN] npm install failed. The existing frontend\dist may still work.
  ) else (
    call "%NPM_CMD%" run build
    if errorlevel 1 echo [WARN] npm run build returned an error. Check frontend\npm-build.log.
    popd
  )
) else (
  echo [4/4] Node.js/npm not found - skipping frontend build.
  if exist "frontend\dist\index.html" (
    echo       Existing frontend\dist will be used.
  ) else (
    echo [WARN] frontend\dist is missing. Install Node.js and run:
    echo        cd frontend ^&^& npm install ^&^& npm run build
  )
)

echo.
echo Checking Tesseract OCR...
set "TESS="
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESS if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe"
if defined TESS (
  echo       Found: %TESS%
) else (
  echo [WARN] Tesseract not found. OCR for scanned PDFs will be unavailable.
  echo        Install from https://github.com/UB-Mannheim/tesseract/wiki
  echo        and enable the Russian language during installation.
)

echo.
echo Setup complete. Run start.bat
exit /b 0

:find_npm
set "NODE_DIR="
for /f "delims=" %%i in ('where node 2^>nul') do (
  set "NODE_DIR=%%~dpi"
  goto :find_npm_found
)
if exist "%LOCALAPPDATA%\nodejs" (
  for /d %%d in ("%LOCALAPPDATA%\nodejs\node-*") do (
    if exist "%%d\node.exe" (
      set "NODE_DIR=%%d"
      goto :find_npm_found
    )
  )
)
goto :eof

:find_npm_found
if exist "%NODE_DIR%\npm.cmd" (
  set "PATH=%NODE_DIR%;%PATH%"
  set "NPM_CMD=%NODE_DIR%\npm.cmd"
) else (
  set "NPM_CMD=npm"
)
goto :eof

:fail
echo.
echo [ERROR] Setup failed. See messages above.
exit /b 1
