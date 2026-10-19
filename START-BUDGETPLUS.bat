@echo off
cd /d "%~dp0"
if errorlevel 1 (
    echo Could not open the BudgetPlus project folder.
    pause
    exit /b 1
)
setlocal

if not exist ".\backend\.venv\Scripts\python.exe" (
    echo BudgetPlus backend Python was not found.
    goto :failed
)
if not exist ".\.tools\node-v22.16.0-win-x64\node.exe" (
    echo BudgetPlus bundled Node was not found.
    goto :failed
)
if not exist ".\.tools\node-v22.16.0-win-x64\npm.cmd" (
    echo BudgetPlus bundled npm was not found.
    goto :failed
)

rem Kill stale process trees and verify both ports are free before starting.
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $deadline = [DateTime]::UtcNow.AddSeconds(30); do { $listeners = @([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -in 5173,8000 }); if ($listeners.Count -eq 0) { exit 0 }; $connections = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in 5173,8000 }); $owners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique); foreach ($owner in $owners) { if ($owner -gt 0) { taskkill.exe /PID $owner /T /F | Out-Null } }; Start-Sleep -Milliseconds 500 } while ([DateTime]::UtcNow -lt $deadline); Write-Host 'Ports 5173 or 8000 are still in use.'; exit 1 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo Could not stop an old server. Try STOP-BUDGETPLUS.bat as administrator.
    goto :failed
)

echo Starting BudgetPlus backend...
start "BudgetPlus Backend" /D "%CD%" "%ComSpec%" /D /K ".\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload"
if errorlevel 1 goto :backendFailed
call :waitForPort 8000
if errorlevel 1 goto :backendFailed
echo Backend ready.

echo Starting BudgetPlus frontend...
set "PATH=%CD%\.tools\node-v22.16.0-win-x64;%PATH%"
start "BudgetPlus Frontend" /D "%CD%" "%ComSpec%" /D /K "npm.cmd run dev"
if errorlevel 1 goto :frontendFailed
call :waitForPort 5173
if errorlevel 1 goto :frontendFailed
echo Frontend ready.

echo Opening BudgetPlus...
start "" "http://localhost:5173"
exit /b 0

:waitForPort
rem Allow up to two minutes. Require a listening port and an HTTP response:
rem uvicorn's reload process can bind its socket before the app is ready.
powershell.exe -NoLogo -NoProfile -Command "$deadline = [DateTime]::UtcNow.AddSeconds(120); do { $listening = @([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq %~1 }).Count -gt 0; if ($listening) { try { $request = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:%~1/'); $request.Proxy = $null; $request.Timeout = 2000; $response = $request.GetResponse(); $response.Close(); exit 0 } catch [System.Net.WebException] { if ($null -ne $_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode; $_.Exception.Response.Close(); if ($status -lt 500) { exit 0 } } } catch {} }; Start-Sleep -Milliseconds 500 } while ([DateTime]::UtcNow -lt $deadline); exit 1"
exit /b %errorlevel%

:backendFailed
echo The backend did not become ready within two minutes.
echo Check the BudgetPlus Backend window for the error.
goto :failed

:frontendFailed
echo The frontend did not become ready within two minutes.
echo Check the BudgetPlus Frontend window for the error.
goto :failed

:failed
echo BudgetPlus could not start. The server windows will stay open.
pause
exit /b 1
