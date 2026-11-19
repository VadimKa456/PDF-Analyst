@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  PDF Analyst - desktop build
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  exit /b 1
)

set "PY=.venv\Scripts\python.exe"
set "PIP=.venv\Scripts\pip.exe"

echo [1/5] Installing desktop build dependencies...
"%PIP%" install --upgrade pip
if exist "requirements-desktop.txt" (
  "%PIP%" install -r requirements-desktop.txt
) else (
  "%PIP%" install pyinstaller==6.* pywebview==5.*
)
if errorlevel 1 goto :fail

if not exist "frontend\dist\index.html" (
  echo [2/5] Building frontend...
  set "NPM_CMD="
  where npm >nul 2>nul
  if not errorlevel 1 set "NPM_CMD=npm"
  if not defined NPM_CMD (
    for /d %%d in ("%LOCALAPPDATA%\nodejs\node-*") do (
      if exist "%%d\npm.cmd" set "NPM_CMD=%%d\npm.cmd"
    )
  )
  if not defined NPM_CMD (
    for /f "delims=" %%i in ('where node 2^>nul') do (
      if exist "%%~dpi\npm.cmd" set "NPM_CMD=%%~dpi\npm.cmd"
    )
  )
  if not defined NPM_CMD (
    echo [ERROR] Frontend dist is missing and npm not found.
    echo         Install Node.js or provide frontend\dist.
    exit /b 1
  )
  pushd frontend
  call "%NPM_CMD%" install
  call "%NPM_CMD%" run build
  popd
) else (
  echo [2/5] Frontend dist found - skipping build.
)

echo [3/5] Running PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean pdf_analyst.spec
if errorlevel 1 goto :fail

echo [4/5] Copying runtime notes...
if not exist "dist\PDF Analyst" (
  echo [ERROR] Build output not found: dist\PDF Analyst
  exit /b 1
)
if exist ".env.example" copy /Y ".env.example" "dist\PDF Analyst\.env.example" >nul
if exist "LICENSE" copy /Y "LICENSE" "dist\PDF Analyst\LICENSE" >nul
if exist "DESKTOP_BUILD.md" copy /Y "DESKTOP_BUILD.md" "dist\PDF Analyst\DESKTOP_BUILD.md" >nul

echo [5/5] Building installer (Inno Setup)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)
if defined ISCC (
  "%ISCC%" /Qp "installer.iss"
  if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed.
    exit /b 1
  )
  echo Installer created in dist\installer\
) else (
  echo [INFO] Inno Setup 6 not found. Installing via winget...
  winget install JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --silent
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if defined ISCC (
    "%ISCC%" /Qp "installer.iss"
    if errorlevel 1 exit /b 1
    echo Installer created in dist\installer\
  ) else (
    echo [ERROR] Cannot find ISCC.exe after install.
    exit /b 1
  )
)
if not exist "dist\installer\PDF-Analyst-Setup.exe" (
  echo [ERROR] Installer EXE not produced.
  exit /b 1
)

echo.
echo Done. Portable app: dist\PDF Analyst\PDF Analyst.exe
exit /b 0

:fail
echo.
echo [ERROR] Build failed.
exit /b 1
