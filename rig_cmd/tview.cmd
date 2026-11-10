@echo off
setlocal EnableExtensions DisableDelayedExpansion
"%~dp0..\runtime\python310\python.exe" -I -m moteus_gui.tview %*
exit /b %ERRORLEVEL%
