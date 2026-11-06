@echo off
setlocal
cd /d "%~dp0.."
set "LAUNCH_ARGS=--launch"
if "%~1"=="--check" set "LAUNCH_ARGS="
set "GAME_PYTHON="
if exist "%~dp0build\python.txt" set /p GAME_PYTHON=<"%~dp0build\python.txt"
if defined GAME_PYTHON if exist "%GAME_PYTHON%" (
  "%GAME_PYTHON%" "%~dp0build_launcher.py" %LAUNCH_ARGS%
  goto finished
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "%~dp0build_launcher.py" %LAUNCH_ARGS%
  goto finished
)
where python >nul 2>&1
if not errorlevel 1 (
  python "%~dp0build_launcher.py" %LAUNCH_ARGS%
  goto finished
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0build_launcher.py" %LAUNCH_ARGS%
  goto finished
)
if exist "%~dp0build\current.txt" (
  set /p LAUNCHER_NAME=<"%~dp0build\current.txt"
  goto existing
)
echo Python is required. Install Python or restore this project's environment.
pause
exit /b 1
:existing
if "%~1"=="--check" (
  echo %~dp0build\%LAUNCHER_NAME%
  exit /b 0
)
start "" "%~dp0build\%LAUNCHER_NAME%"
exit /b 0
:finished
set "LAUNCH_EXIT=%ERRORLEVEL%"
if "%~1"=="--check" exit /b %LAUNCH_EXIT%
if errorlevel 1 pause
exit /b %LAUNCH_EXIT%
