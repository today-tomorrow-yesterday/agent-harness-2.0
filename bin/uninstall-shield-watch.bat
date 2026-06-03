@echo off
REM uninstall-shield-watch.bat
REM
REM Removes the AgentShield-Watch scheduled task and stops any running instance.

echo Stopping AgentShield-Watch if running...
schtasks /End /TN "AgentShield-Watch" 2>nul

echo Deleting AgentShield-Watch task...
schtasks /Delete /TN "AgentShield-Watch" /F

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FAILED to remove task (it may not have been registered).
    pause
    exit /b 1
)

echo.
echo AgentShield-Watch removed.
echo.
echo Log file at Z:\agent-os\agentshield-watch.log is preserved.
echo State at Z:\agent-os\bin\shield-state.json is preserved.
echo Delete those manually if you want a clean slate.
echo.
pause
