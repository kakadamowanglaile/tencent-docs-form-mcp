$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $VenvPath
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv $VenvPath
} else {
    throw "未找到 Python。请先安装 Python 3.10 或更高版本。"
}

& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host "安装完成。Python: $PythonPath"
