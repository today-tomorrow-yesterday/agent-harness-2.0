@echo off
REM install-shield-watch.bat
REM
REM Registers shield-watch.ps1 as a Scheduled Task that runs at user login.
REM Runs in a hidden window so it doesn't pop up a console every time you log in.
REM No admin required — this is a user-scoped task.
REM
REM Run once:
REM   Z:\agent-os\bin\install-shield-watch.bat
REM
REM To remove later:
REM   Z:\agent-os\bin\uninstall-shield-watch.bat
REM
REM To trigger it manually right now (without rebooting):
REM   schtasks /Run /TN AgentShield-Watch
REM
REM To check status:
REM   schtasks /Query /TN AgentShield-Watch /V /FO LIST

echo Registering AgentShield-Watch scheduled task...

schtasks /Create ^
  /SC ONLOGON ^
  /TN "AgentShield-Watch" ^
  /TR "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1" ^
  /RL LIMITED ^
  /F

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FAILED to register task.
    pause
    exit /b 1
)

echo.
echo Task registered. It will run automatically on your next login.
echo.
echo To start it right now without rebooting:
echo     schtasks /Run /TN AgentShield-Watch
echo.
echo To stop it:
echo     schtasks /End /TN AgentShield-Watch
echo.
echo To remove it permanently:
echo     Z:\agent-os\bin\uninstall-shield-watch.bat
echo.
pause
