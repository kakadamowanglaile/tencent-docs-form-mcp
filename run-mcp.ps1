$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ServerPath = Join-Path $ProjectRoot "server.py"

if (-not (Test-Path $PythonPath)) {
    [Console]::Error.WriteLine("未找到项目虚拟环境，请先执行 .\install-windows.ps1")
    exit 1
}

& $PythonPath $ServerPath
exit $LASTEXITCODE
