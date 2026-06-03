@echo off
REM uninstall-shield-watch-noadmin.bat
REM
REM Removes the Startup-folder shortcut. No admin required.

echo Removing AgentShield-Watch shortcut from Startup folder...

del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AgentShield-Watch.lnk" 2>nul

if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AgentShield-Watch.lnk" (
    echo.
    echo FAILED — shortcut still present. Delete manually from:
    echo     %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
    pause
    exit /b 1
)

echo Shortcut removed.
echo.
echo NOTE: If shield-watch.ps1 is currently running in the background, you
echo can stop it via Task Manager (look for powershell.exe with shield-watch
echo in command line), or just reboot — it won't auto-restart.
echo.
echo The log and state file are preserved at:
echo     Z:\agent-os\agentshield-watch.log
echo     Z:\agent-os\bin\shield-state.json
echo.
pause
