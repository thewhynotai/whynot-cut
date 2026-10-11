@echo off
rem Test-only uv stand-in (see fake_uv.py). Runs fake_uv.py with %FAKE_UV_PYTHON% (default: python).
setlocal
set "PY=%FAKE_UV_PYTHON%"
if "%PY%"=="" set "PY=python"
"%PY%" -B "%~dp0fake_uv.py" %*
exit /b %ERRORLEVEL%
