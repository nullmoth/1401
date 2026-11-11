@echo off
rem Build the packaged Windows release: prepare, verify on the packaged runtime, package, hash.
rem Needs GH_TOKEN in the environment for GitHub API calls.
setlocal
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set PYTHONDONTWRITEBYTECODE=1

call scripts\with-msvc.cmd .venv\Scripts\python.exe tools\windows_release.py prepare --stage out\release-stage --cache out\release-cache --compiled build\1401-compiled-291\1401.exe
if errorlevel 1 exit /b 1

out\release-stage\1401\engine\python\python.exe -B tools\check_windows_package.py --stage out\release-stage --repo . --cache out\release-cache --output reports\tests\windows-verification.json
if errorlevel 1 (
  echo Packaged verification failed; see reports\tests\windows-verification.json
  exit /b 1
)

out\release-stage\1401\engine\python\python.exe -B tools\windows_release.py package --stage out\release-stage --evidence reports\tests\windows-verification.json --output out\release-artifact
if errorlevel 1 exit /b 1

powershell -NoProfile -Command "Get-ChildItem out\release-artifact | ForEach-Object { $h = Get-FileHash $_.FullName -Algorithm SHA256; '{0}  {1}' -f $h.Hash.ToLower(), $_.Name }"
exit /b 0
