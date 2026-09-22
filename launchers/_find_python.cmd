@echo off
rem Locate a usable python interpreter. Sets PYEXE.
set "PYEXE="
for %%V in (313 312 311 310) do (
  if not defined PYEXE (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
      set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    )
  )
)
if not defined PYEXE (
  for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PYEXE set "PYEXE=%%i"
  )
)
if not defined PYEXE (
  echo Python 3 was not found. Install it from https://python.org
  exit /b 1
)
