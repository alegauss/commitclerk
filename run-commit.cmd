@echo off
setlocal

set SCRIPT_DIR=%~dp0

if "%OPENAI_API_KEY%"=="" (
    echo Error: OPENAI_API_KEY is not set.
    exit /b 2
)

REM -A, not a glob: a glob skips dotfiles and never records deletions.
git add -A
if errorlevel 1 (
    echo git add failed.
    exit /b 1
)

REM Works whether this wrapper sits next to the package (a repo checkout) or next
REM to a downloaded single-file dist/commitclerk.py: -m finds either on the path.
set PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%
python -m commitclerk %*

endlocal
