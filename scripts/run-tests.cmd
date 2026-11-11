@echo off
rem Run the Python suite with the MSVC environment the native C fixture tests need.
rem Usage: scripts\run-tests.cmd [unittest args...]
setlocal
cd /d "%~dp0.."
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
)
if defined VSDIR if exist "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1
if "%~1"=="" (
  .venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py" -b
) else (
  .venv\Scripts\python.exe -m unittest %*
)
exit /b %errorlevel%
