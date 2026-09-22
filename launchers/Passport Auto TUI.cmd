@echo off
title Passport Auto - Control Panel
cd /d "%~dp0"
call "%~dp0_find_python.cmd" || pause
"%PYEXE%" "%~dp0pa_tui.py"
if errorlevel 1 pause
