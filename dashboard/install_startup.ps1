$ErrorActionPreference = "Stop"

$TaskName = "AI House Dashboard"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ServerPath = Join-Path $PSScriptRoot "server.py"
$PythonExe = (Get-Command python -ErrorAction Stop).Source

$StartupFolder = Join-Path $env:LOCALAPPDATA "AIHouse"
New-Item -ItemType Directory -Path $StartupFolder -Force | Out-Null
$VbsPath = Join-Path $StartupFolder "start_dashboard.vbs"

$Command = '"' + $PythonExe + '" "' + $ServerPath + '"'
$EscapedCommand = $Command.Replace('"', '""')
$EscapedWorkingDirectory = $ProjectRoot.Replace('"', '""')
$NewLine = [Environment]::NewLine
$VbsContent = 'Set WshShell = CreateObject("WScript.Shell")' + $NewLine +
    'WshShell.CurrentDirectory = "' + $EscapedWorkingDirectory + '"' + $NewLine +
    'WshShell.Run "' + $EscapedCommand + '", 0, False'
[System.IO.File]::WriteAllText($VbsPath, $VbsContent, [System.Text.UTF8Encoding]::new($false))

$WscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
$Action = New-ScheduledTaskAction -Execute $WscriptExe -Argument ('"' + $VbsPath + '"') -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Starts the local AI House dashboard and automatically resumes autonomy unless the owner has stopped it." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "AI House is set to start when you sign in to Windows."
Write-Host "Dashboard: http://127.0.0.1:8000"
Write-Host "Autonomy starts automatically unless you have pressed Stop autonomy."
