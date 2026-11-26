$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Reproducible Windows OCR test dependency:
# - Official Tesseract 5.5.3 Windows installer, SHA-256 pinned.
# - Official tessdata_fast Russian model pinned by immutable Git commit + blob SHA.
$installerUrl = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe"
$installerSha256 = "BEE9E3434BD94FD65387D9BE28CD467A41F61B1275383B55B0F59A1331270AE4"
$tessdataCommit = "87416418657359cb625c412a48b6e1d6d41c29bd"
$rusBlobSha = "b146cb2263acbc6383f8e92ea0ce759537687bb8"
$rusSize = 3861738

$installer = Join-Path $env:RUNNER_TEMP "tesseract-ocr-w64-setup-5.5.3.20260724.exe"
Write-Host "Downloading official Tesseract 5.5.3 Windows installer..."
Invoke-WebRequest -Uri $installerUrl -OutFile $installer

$actualInstallerSha = (Get-FileHash -Path $installer -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualInstallerSha -ne $installerSha256) {
    throw "Tesseract installer SHA-256 mismatch. Actual: $actualInstallerSha"
}

Write-Host "Installing Tesseract silently..."
$process = Start-Process -FilePath $installer -ArgumentList "/S" -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Tesseract installer exited with code $($process.ExitCode)"
}

$tesseract = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (-not (Test-Path -LiteralPath $tesseract -PathType Leaf)) {
    throw "Tesseract executable was not found at the expected path: $tesseract"
}

$tessdata = Join-Path (Split-Path -Parent $tesseract) "tessdata"
if (-not (Test-Path -LiteralPath $tessdata -PathType Container)) {
    throw "Tesseract tessdata directory is missing: $tessdata"
}

$rusModel = Join-Path $env:RUNNER_TEMP "rus.traineddata"
$rusUrl = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$tessdataCommit/rus.traineddata"
Write-Host "Downloading Russian tessdata_fast model pinned to $tessdataCommit..."
Invoke-WebRequest -Uri $rusUrl -OutFile $rusModel

$rusLength = (Get-Item -LiteralPath $rusModel).Length
if ($rusLength -ne $rusSize) {
    throw "Russian traineddata size mismatch. Expected $rusSize bytes, got $rusLength"
}

# Git computes the canonical Git blob object ID (SHA-1 over 'blob <size>\0<bytes>').
# Pinning both the source commit and blob ID ensures the downloaded language model
# exactly matches the reviewed upstream file.
$actualBlobSha = (& git hash-object -- $rusModel).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0) {
    throw "git hash-object failed while verifying rus.traineddata"
}
if ($actualBlobSha -ne $rusBlobSha) {
    throw "Russian traineddata Git blob SHA mismatch. Actual: $actualBlobSha"
}

Copy-Item -LiteralPath $rusModel -Destination (Join-Path $tessdata "rus.traineddata") -Force

# Expose the executable to later GitHub Actions steps and pytest/pytesseract.
$tesseractDir = Split-Path -Parent $tesseract
Add-Content -Path $env:GITHUB_ENV -Value "TESSERACT_CMD=$tesseract"
Add-Content -Path $env:GITHUB_ENV -Value "TESSDATA_PREFIX=$tessdata"
Add-Content -Path $env:GITHUB_PATH -Value $tesseractDir
$env:TESSERACT_CMD = $tesseract
$env:TESSDATA_PREFIX = $tessdata
$env:Path = "$tesseractDir;$env:Path"

$languages = (& $tesseract --list-langs 2>&1 | Out-String)
Write-Host $languages
if ($LASTEXITCODE -ne 0) {
    throw "Tesseract --list-langs failed"
}
if ($languages -notmatch "(?m)^eng\s*$") {
    throw "English Tesseract language data was not installed"
}
if ($languages -notmatch "(?m)^rus\s*$") {
    throw "Russian Tesseract language data was not installed"
}

$version = (& $tesseract --version 2>&1 | Select-Object -First 1)
Write-Host "Verified OCR engine: $version"
Write-Host "Verified rus.traineddata: $rusBlobSha"
