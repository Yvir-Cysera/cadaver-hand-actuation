@echo off
setlocal EnableExtensions DisableDelayedExpansion
"%~dp0..\runtime\python310\python.exe" -I -m moteus.moteus_tool %*
exit /b %ERRORLEVEL%
