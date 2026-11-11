@echo off
rem Run one command with the Visual Studio x64 build environment loaded.
rem Usage: scripts\with-msvc.cmd <command> [args...]
setlocal
cd /d "%~dp0.."
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
)
if defined VSDIR if exist "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul
%*
exit /b %errorlevel%
