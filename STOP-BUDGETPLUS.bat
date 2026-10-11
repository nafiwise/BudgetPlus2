@echo off
cd /d "%~dp0"
if errorlevel 1 (
    echo Could not open the BudgetPlus project folder.
    pause
    exit /b 1
)
setlocal

rem Kill listener process trees, retry, and verify both ports are free.
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $deadline = [DateTime]::UtcNow.AddSeconds(30); do { $listeners = @([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -in 5173,8000 }); if ($listeners.Count -eq 0) { exit 0 }; $connections = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in 5173,8000 }); $owners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique); foreach ($owner in $owners) { if ($owner -gt 0) { taskkill.exe /PID $owner /T /F | Out-Null } }; Start-Sleep -Milliseconds 500 } while ([DateTime]::UtcNow -lt $deadline); Write-Host 'Ports 5173 or 8000 are still in use.'; exit 1 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo Could not stop BudgetPlus. Right-click this file and choose Run as administrator.
    pause
    exit /b 1
)

echo BudgetPlus stopped.
exit /b 0
