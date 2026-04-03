param(
    [string]$PythonPath = "C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe"
)

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $projectRoot "main_gui.py"

if (-not (Test-Path $PythonPath)) {
    Write-Host "Python not found at: $PythonPath" -ForegroundColor Red
    Write-Host "Update the -PythonPath argument in run_gui.ps1." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "main_gui.py not found at: $scriptPath" -ForegroundColor Red
    exit 1
}

& $PythonPath $scriptPath
