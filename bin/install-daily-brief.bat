@echo off
REM Install the Daily-Brief scheduled task (Windows Task Scheduler, user-scoped, no admin).
REM Runs daily at 07:00 local (after the morning farmers at 06:00-06:30). Assembles a
REM cheap LLM-FREE digest of farmer activity + inbox + news lane and posts it to Slack
REM (no-op until bin\secrets\slack-webhook.txt holds a real webhook). Zero API cost.

setlocal

set TASK_NAME=Daily-Brief
set SCRIPT_PATH=Z:\agent-os\bin\daily-brief.py
REM Full path to the MS Store Python (bare python3.exe is a WindowsApps alias
REM stub that Scheduled Task contexts can't resolve -- fails 0x80070002).
set PYTHON_EXE=C:\Users\<USERNAME>\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe

if not exist "%SCRIPT_PATH%" (
    echo ERROR: %SCRIPT_PATH% not found.
    exit /b 1
)
if not exist "%PYTHON_EXE%" (
    echo ERROR: %PYTHON_EXE% not found.
    exit /b 1
)

schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "\"%PYTHON_EXE%\" \"%SCRIPT_PATH%\"" ^
    /SC DAILY ^
    /ST 07:00 ^
    /F

if errorlevel 1 (
    echo ERROR: schtasks /Create failed.
    exit /b 1
)

echo.
echo OK -- Daily-Brief registered. Runs daily at 07:00 local time.
echo Posts to Slack once bin\secrets\slack-webhook.txt holds a real webhook (see that folder's README).
echo To run on-demand:   schtasks /Run /TN "%TASK_NAME%"
echo To preview output:  python "%SCRIPT_PATH%" --print
echo.
endlocal
