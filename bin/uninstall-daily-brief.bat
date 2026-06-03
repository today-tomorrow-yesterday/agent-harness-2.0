@echo off
REM Remove the Daily-Brief scheduled task. Preserves the script + daily-brief.md.
setlocal
set TASK_NAME=Daily-Brief
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
    echo ERROR: could not delete %TASK_NAME% (may not exist).
    exit /b 1
)
echo OK -- %TASK_NAME% removed. daily-brief.py and daily-brief.md are preserved.
endlocal
