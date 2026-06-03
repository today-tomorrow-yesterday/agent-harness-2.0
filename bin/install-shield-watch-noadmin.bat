@echo off
REM install-shield-watch-noadmin.bat
REM
REM No-admin alternative to install-shield-watch.bat. Drops a shortcut into the
REM user's Windows Startup folder so shield-watch.ps1 runs at every login.
REM
REM Pros: No admin / UAC required.
REM Cons: Less robust than a Scheduled Task — depends on Explorer at login,
REM       and is harder to manage via schtasks.exe. For most personal setups,
REM       these tradeoffs don't matter.
REM
REM To remove: Z:\agent-os\bin\uninstall-shield-watch-noadmin.bat
REM            or delete the shortcut manually from the Startup folder
REM            (Win+R, type:  shell:startup  )

echo Installing AgentShield-Watch via Startup folder...

powershell -ExecutionPolicy Bypass -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\AgentShield-Watch.lnk\"); $sc.TargetPath = 'powershell.exe'; $sc.Arguments = '-WindowStyle Hidden -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1'; $sc.WorkingDirectory = 'Z:\agent-os\bin'; $sc.WindowStyle = 7; $sc.Description = 'AgentShield security watcher'; $sc.Save(); Write-Host 'Shortcut created at:' $sc.FullName"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FAILED to create shortcut.
    pause
    exit /b 1
)

echo.
echo Installed. It will run on your next login.
echo.
echo To start it right now without rebooting:
echo     powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1
echo.
echo (That will run in the foreground of whatever shell you launch it from.
echo  Close the shell to stop it. On next login it auto-starts from the Startup folder.)
echo.
echo To remove permanently:
echo     Z:\agent-os\bin\uninstall-shield-watch-noadmin.bat
echo.
pause
