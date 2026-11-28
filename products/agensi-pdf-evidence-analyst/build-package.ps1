# Build the Agensi ZIP package from the checked-in Skill sources.
# Run from any PowerShell location after checking out this branch:
#   powershell -ExecutionPolicy Bypass -File .\products\agensi-pdf-evidence-analyst\build-package.ps1

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$sourceDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $sourceDir "..\..\..")).Path
$distDir = Join-Path $repoRoot "dist"
$stageRoot = Join-Path $env:TEMP ("pdf-evidence-analyst-" + [guid]::NewGuid().ToString("N"))
$packageDir = Join-Path $stageRoot "PDF-Evidence-Analyst"
$zipPath = Join-Path $distDir "PDF-Evidence-Analyst-Agensi-v1.0.0.zip"

$required = @(
    "SKILL.md",
    "references\analysis-protocol.md",
    "references\report-template.md",
    "references\quality-checklist.md"
)

try {
    foreach ($relativePath in $required) {
        $fullPath = Join-Path $sourceDir $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw "Required package file is missing: $fullPath"
        }
    }

    $skillText = Get-Content -LiteralPath (Join-Path $sourceDir "SKILL.md") -Raw -Encoding UTF8
    if ($skillText -notmatch '(?m)^name:\s*PDF Evidence Analyst\s*$') {
        throw "SKILL.md is missing the expected name metadata."
    }
    if ($skillText -notmatch '(?m)^description:\s*.+$') {
        throw "SKILL.md is missing the required description metadata."
    }

    New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
    foreach ($relativePath in $required) {
        $destination = Join-Path $packageDir $relativePath
        $destinationParent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceDir $relativePath) -Destination $destination
    }

    New-Item -ItemType Directory -Path $distDir -Force | Out-Null
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $stageRoot,
        $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $entries = @($archive.Entries | Where-Object { -not $_.FullName.EndsWith("/") } | ForEach-Object { $_.FullName.Replace("\\", "/") } | Sort-Object)
        $expected = @(
            "PDF-Evidence-Analyst/SKILL.md",
            "PDF-Evidence-Analyst/references/analysis-protocol.md",
            "PDF-Evidence-Analyst/references/quality-checklist.md",
            "PDF-Evidence-Analyst/references/report-template.md"
        ) | Sort-Object

        if (($entries -join "|") -ne ($expected -join "|")) {
            throw "ZIP contents do not match the expected four-file package. Found: $($entries -join ', ')"
        }

        foreach ($entry in $archive.Entries) {
            if (-not $entry.FullName.EndsWith("/")) {
                $stream = $entry.Open()
                try {
                    $buffer = New-Object byte[] 8192
                    while ($stream.Read($buffer, 0, $buffer.Length) -gt 0) { }
                }
                finally {
                    $stream.Dispose()
                }
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    Write-Host "Package created and verified:" -ForegroundColor Green
    Write-Host $zipPath
    Write-Host "Files: $($required.Count); ZIP read test: passed"
}
finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
