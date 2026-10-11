@echo off
rem Test-only Claude Code CLI stand-in (see fake_claude.py). Runs fake_claude.py with %FAKE_CLAUDE_PYTHON% (default: python).
setlocal
set "PY=%FAKE_CLAUDE_PYTHON%"
if "%PY%"=="" set "PY=python"
"%PY%" -B "%~dp0fake_claude.py" %*
exit /b %ERRORLEVEL%
