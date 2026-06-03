@echo off
REM Remove the Brain-Embed scheduled task. Preserves the script and its log.
setlocal
set TASK_NAME=Brain-Embed
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
    echo ERROR: could not delete %TASK_NAME% (may not exist).
    exit /b 1
)
echo OK -- %TASK_NAME% removed. brain-embed.ps1 and its log are preserved.
endlocal
