@echo off
REM Install the Brain-Embed scheduled task (Windows Task Scheduler, user-scoped, no admin).
REM Runs daily at 05:00 local (after Farmer-Distill at 04:00). Backfills semantic
REM embeddings for transcripts the bulk ingest left unembedded. LOCAL compute only
REM (BGE model) -- zero subscription / API cost.

setlocal

set TASK_NAME=Brain-Embed
set SCRIPT_PATH=Z:\agent-os\bin\brain-embed.ps1

if not exist "%SCRIPT_PATH%" (
    echo ERROR: %SCRIPT_PATH% not found.
    exit /b 1
)

schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT_PATH%\"" ^
    /SC DAILY ^
    /ST 05:00 ^
    /F

if errorlevel 1 (
    echo ERROR: schtasks /Create failed.
    exit /b 1
)

echo.
echo OK -- Brain-Embed registered. Runs daily at 05:00 local time.
echo To run on-demand:   schtasks /Run /TN "%TASK_NAME%"
echo To check status:    schtasks /Query /TN "%TASK_NAME%" /V /FO LIST
echo Log:                Z:\agent-os\claude-brain\logs\^<hostname^>\batch_embed.log
echo.
endlocal
