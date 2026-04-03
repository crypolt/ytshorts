@echo off
setlocal

set PYTHON_EXE=C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe
set SCRIPT=%~dp0main_gui.py
set REQUIREMENTS=%~dp0requirements.txt

if not exist "%PYTHON_EXE%" (
  echo Python not found at: %PYTHON_EXE%
  echo Edit run_gui.bat and update PYTHON_EXE.
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo main_gui.py not found at: %SCRIPT%
  exit /b 1
)

"%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS%"
"%PYTHON_EXE%" "%SCRIPT%"
