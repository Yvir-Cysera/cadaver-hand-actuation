@echo off
setlocal EnableExtensions DisableDelayedExpansion
if /i "%~1"=="--help" goto :help
if not "%~1"=="" goto :usage_error
if not exist "%~dp0runtime\python310\python.exe" (
    >&2 echo Missing bundled Python: "%~dp0runtime\python310\python.exe"
    >&2 echo Copy the complete Towles_lab folder, including runtime.
    exit /b 1
)
pushd "%~dp0" || exit /b 1
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "VIRTUAL_ENV="
set "PATH=%CD%\rig_cmd;%CD%\runtime\python310;%PATH%"
set "PROMPT=(Towles_lab) $P$G"
echo Towles_lab command prompt. Type exit to return.
echo Python: "%CD%\runtime\python310\python.exe"
echo Commands: python, python -m pip, tview, moteus_tool
"%ComSpec%" /d /v:off
set "_status=%ERRORLEVEL%"
popd
exit /b %_status%

:help
echo Start RES.cmd with no arguments to open the rig command prompt.
echo Inside it: python, python -m pip, tview, moteus_tool
echo For one command without a prompt, call runtime\python310\python.exe
echo or rig_cmd\tview.cmd or rig_cmd\moteus_tool.cmd directly.
exit /b 0

:usage_error
>&2 echo RES.cmd opens a command prompt. Use RES.cmd --help for usage.
exit /b 2
