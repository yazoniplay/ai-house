$ErrorActionPreference = "Stop"

$TaskName = "AI House Dashboard"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ServerPath = Join-Path $PSScriptRoot "server.py"

$PythonCommand = Get-Command python -ErrorAction Stop
$PythonExe = $PythonCommand.Source
$PythonwExe = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
if (Test-Path $PythonwExe) {
    $PythonExe = $PythonwExe
}

$Arguments = '"' + $ServerPath + '"'
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Starts the local AI House dashboard and automatically resumes autonomy unless the owner has stopped it." -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "AI House is set to start when you sign in to Windows."
Write-Host "Dashboard: http://127.0.0.1:8000"
Write-Host "Autonomy starts automatically unless you have pressed Stop autonomy."
