@echo off
setlocal
cd /d "%~dp0"
python fetch_storm_maps.py
exit /b %errorlevel%
