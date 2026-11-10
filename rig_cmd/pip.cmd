@echo off
setlocal EnableExtensions DisableDelayedExpansion
"%~dp0..\runtime\python310\python.exe" -I -m pip %*
exit /b %ERRORLEVEL%
