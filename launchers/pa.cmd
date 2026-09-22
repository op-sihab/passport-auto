@echo off
rem pa.cmd - run the Passport Auto CLI from this folder:  pa status
setlocal
call "%~dp0_find_python.cmd"
"%PYEXE%" "%~dp0pa.py" %*
