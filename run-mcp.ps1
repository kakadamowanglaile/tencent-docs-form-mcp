$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ServerPath = Join-Path $ProjectRoot "gateway.py"

if (-not (Test-Path $PythonPath)) {
    [Console]::Error.WriteLine("Project virtual environment not found. Run .\install-windows.ps1 first.")
    exit 1
}

& $PythonPath $ServerPath
exit $LASTEXITCODE
