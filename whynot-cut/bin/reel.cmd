@echo off
rem WhyNot Cut engine wrapper for Windows PowerShell / cmd (bin\ is on PATH while the plugin is enabled).
setlocal EnableExtensions
set "HERE=%~dp0.."
set "HOME_DIR=%WHYNOT_HOME%"
if not defined HOME_DIR set "HOME_DIR=%CLAUDE_PLUGIN_OPTION_ENGINE_HOME%"
if not defined HOME_DIR set "HOME_DIR=%REEL_HOME%"
if not defined HOME_DIR set "HOME_DIR=%CLAUDE_PLUGIN_OPTION_REEL_HOME%"
if not defined HOME_DIR (
  set "HOME_DIR=%USERPROFILE%\.whynot-cut"
  if not exist "%USERPROFILE%\.whynot-cut" if exist "%USERPROFILE%\.reel-editor\venv" set "HOME_DIR=%USERPROFILE%\.reel-editor"
)
set "WHYNOT_HOME=%HOME_DIR%"
set "PY=%HOME_DIR%\venv\Scripts\python.exe"
if not exist "%PY%" (
  if /I "%~1"=="setup" (
    echo WhyNot Cut: no engine yet - creating it in %HOME_DIR% ^(a few minutes, ~400 MB^)... 1>&2
    where py >nul 2>nul && (py -3 "%HERE%\setup\setup_env.py" --home "%HOME_DIR%" 1>&2) || (python "%HERE%\setup\setup_env.py" --home "%HOME_DIR%" 1>&2)
  )
)
if not exist "%PY%" goto :blocked
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
"%PY%" "%HERE%\engine\reel\cli.py" %*
exit /b %ERRORLEVEL%

:blocked
rem every blocked message names this plugin and its version, so a wrong `reel` on PATH is recognisable
set "TAG=WhyNot Cut"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%HERE%\.claude-plugin\plugin.json' | ConvertFrom-Json).version" 2^>nul`) do set "TAG=WhyNot Cut %%v"
echo {"blocked": "%TAG%: engine not installed", "how": "install Python 3.10-3.12 (winget install Python.Python.3.12), then run: reel setup"}
exit /b 2
