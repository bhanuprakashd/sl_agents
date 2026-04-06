@echo off
REM SL Agents — Start API Server
REM Usage: start.bat [port]

set PORT=%1
if "%PORT%"=="" set PORT=8080

cd /d "%~dp0"

REM Kill any existing process on the port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo   Killing existing process on port %PORT% (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

echo ============================================================
echo   SL Agents — Event Pipeline Server
echo   Starting on http://localhost:%PORT%
echo   Dashboard: http://localhost:%PORT%
echo   API Docs:  http://localhost:%PORT%/api/docs
echo ============================================================

REM Activate conda/venv if available
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

python -m uvicorn api:app --host 0.0.0.0 --port %PORT% --timeout-keep-alive 5400
