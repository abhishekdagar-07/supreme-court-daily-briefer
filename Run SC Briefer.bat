@echo off
setlocal
cd /d "%~dp0"
title Supreme Court Daily Briefer

echo ============================================================
echo   Supreme Court of India - Daily Judgment Briefer
echo ============================================================
echo.
echo   Press ENTER to fetch the LATEST court day's judgments,
echo   OR type a specific date and press ENTER.
echo.
echo   Date formats accepted:  DD-MM-YYYY   or   YYYY-MM-DD
echo   Example: 10-12-2025
echo.

set "RUNDATE="
set /p "RUNDATE=Date (blank = latest): "

echo.
if "%RUNDATE%"=="" (
    echo Running for the latest available court day...
    echo.
    py main.py --latest
) else (
    echo Running for %RUNDATE% ...
    echo.
    py main.py --date "%RUNDATE%"
)

echo.
echo ============================================================
echo   Done. Files are in your Desktop "Supreme Court Judgments" folder.
echo ============================================================
echo.
pause
endlocal
