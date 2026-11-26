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
if not exist "requirements-desktop-lock.txt" (
  echo [ERROR] requirements-desktop-lock.txt is missing.
  echo         Run the Desktop lock GitHub Actions job and commit its validated artifact.
  exit /b 1
)

set "PY_BOOTSTRAP=.venv\Scripts\python.exe"
"%PY_BOOTSTRAP%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)"
if errorlevel 1 (
  echo [ERROR] Release packaging requires CPython 3.12 x64.
  echo         Recreate .venv with Python 3.12 and run setup.bat again.
  exit /b 1
)

echo [1/8] Creating a clean release environment...
if exist ".build-venv" rmdir /s /q ".build-venv"
"%PY_BOOTSTRAP%" -m venv .build-venv
if errorlevel 1 goto :fail
set "PY=.build-venv\Scripts\python.exe"

echo [2/8] Installing hash-pinned desktop dependencies...
"%PY%" -m pip install --require-hashes -r requirements-desktop-lock.txt
if errorlevel 1 goto :fail
"%PY%" -m pip check
if errorlevel 1 goto :fail

echo [3/8] Generating isolated synthetic PDF fixtures...
set "PDF_ANALYST_SAMPLES_DIR=%TEMP%\PDF Analyst tests\pdfs"
"%PY%" "samples\generate_samples.py"
if errorlevel 1 goto :fail

echo [3/8] Running backend regression tests in the locked environment...
"%PY%" -m pytest -q
set "PDF_ANALYST_SAMPLES_DIR="
if errorlevel 1 goto :fail

echo [4/8] Preparing frontend assets...
if /I "%PDF_ANALYST_FRONTEND_READY%"=="1" (
  if not exist "frontend\dist\index.html" (
    echo [ERROR] CI marked frontend as ready, but frontend\dist\index.html is missing.
    goto :fail
  )
  echo [INFO] Using the frontend build produced by the pinned Node.js/npm CI step.
) else (
  set "NPM_CMD="
  for /f "delims=" %%i in ('where npm.cmd 2^>nul') do call :try_npm "%%i"
  if defined NPM_CMD (
    pushd frontend
    call "%NPM_CMD%" ci
    if errorlevel 1 (
      popd
      goto :fail
    )
    call "%NPM_CMD%" run build
    if errorlevel 1 (
      popd
      goto :fail
    )
    popd
  ) else (
    if not exist "frontend\dist\index.html" (
      echo [ERROR] Node.js/npm is required to build the frontend.
      goto :fail
    )
    echo [WARN] No working npm.cmd was found. Using the existing frontend\dist.
    echo        Install Node.js 22 and rebuild for a reproducible release.
  )
)

echo [5/8] Running PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean pdf_analyst.spec
if errorlevel 1 goto :fail

echo [6/8] Copying runtime notes...
if not exist "dist\PDF Analyst" (
  echo [ERROR] Build output not found: dist\PDF Analyst
  exit /b 1
)
if exist ".env.example" copy /Y ".env.example" "dist\PDF Analyst\.env.example" >nul
if exist "LICENSE" copy /Y "LICENSE" "dist\PDF Analyst\LICENSE" >nul
if exist "DESKTOP_BUILD.md" copy /Y "DESKTOP_BUILD.md" "dist\PDF Analyst\DESKTOP_BUILD.md" >nul

echo [7/8] Generating dependency inventory and third-party notices...
"%PY%" "tools\generate_compliance_inventory.py" --output-dir "dist\PDF Analyst\compliance" --frontend-node-modules "frontend\node_modules"
if errorlevel 1 goto :fail
if not exist "dist\PDF Analyst\compliance\sbom-python.cdx.json" (
  echo [ERROR] Python SBOM was not generated.
  goto :fail
)
if not exist "dist\PDF Analyst\compliance\sbom-frontend.cdx.json" (
  echo [ERROR] Frontend SBOM was not generated.
  goto :fail
)

echo [8/8] Building installer (Inno Setup)...
if /I "%PDF_ANALYST_SKIP_INSTALLER%"=="1" (
  echo [INFO] Inno Setup step skipped by PDF_ANALYST_SKIP_INSTALLER=1.
  goto :success
)
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

:success
echo.
echo Done. Portable app: dist\PDF Analyst\PDF Analyst.exe
if /I "%PDF_ANALYST_SKIP_INSTALLER%"=="1" echo Installer build intentionally skipped.
exit /b 0

:fail
echo.
echo [ERROR] Build failed.
exit /b 1

:try_npm
if defined NPM_CMD exit /b 0
if not exist "%~1" exit /b 0
call "%~1" --version >nul 2>nul
if not errorlevel 1 set "NPM_CMD=%~1"
exit /b 0
