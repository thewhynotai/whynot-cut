@echo off
rem WhyNot Cut engine wrapper for Windows PowerShell / cmd (bin\ is on PATH while the plugin is enabled).
rem Arguments reach the engine untouched: %* is expanded once, outside any ( ) block, with delayed expansion off, so
rem %, !, ^, ), $ and Arabic in arguments survive. Every path is quoted, also inside blocks.
setlocal EnableExtensions DisableDelayedExpansion
set "HERE=%~dp0.."
rem Engine home, the same order as plat.engine_home(): env > the saved plugin option (the pointer file the SessionStart
rem hook writes; without one, Claude Code's settings.json pluginConfigs) > %USERPROFILE%\.whynot-cut with an engine >
rem a legacy home (.reel-editor, .dr-nahla-editor: still read in 3.x, dropped in 4.0) > %USERPROFILE%\.whynot-cut.
set "HOME_DIR=%WHYNOT_HOME%"
if not defined HOME_DIR set "HOME_DIR=%CLAUDE_PLUGIN_OPTION_ENGINE_HOME%"
if not defined HOME_DIR set "HOME_DIR=%REEL_HOME%"
if not defined HOME_DIR set "HOME_DIR=%CLAUDE_PLUGIN_OPTION_REEL_HOME%"
if not defined HOME_DIR call :saved_home
if not defined HOME_DIR call :default_home
set "WHYNOT_HOME=%HOME_DIR%"
set "PY=%HOME_DIR%\venv\Scripts\python.exe"
if not exist "%PY%" if /I "%~1"=="setup" call :setup
if not exist "%PY%" goto :blocked
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%PY%" "%HERE%\engine\reel\cli.py" %*
exit /b %ERRORLEVEL%

:saved_home
rem engine_home from the pointer file (authoritative when it exists; "" = not set), else from settings.json
rem pluginConfigs["whynot-cut@..."].options. Both are JSON with one key per line; read as UTF-8 (chcp 65001) so an
rem Arabic path survives, then the code page is put back.
set "PTR=%WHYNOT_OPTIONS_FILE%"
if not defined PTR set "PTR=%USERPROFILE%\.whynot-cut\plugin-options.json"
set "CFG=%CLAUDE_CONFIG_DIR%"
if not defined CFG set "CFG=%USERPROFILE%\.claude"
set "SRC="
set "INSIDE="
if exist "%PTR%" set "INSIDE=1"
if exist "%PTR%" set "SRC=%PTR%"
if not defined SRC if exist "%CFG%\settings.json" set "SRC=%CFG%\settings.json"
if not defined SRC exit /b 0
set "OLDCP="
for /f "tokens=2 delims=:." %%c in ('chcp') do set "OLDCP=%%c"
if defined OLDCP set "OLDCP=%OLDCP: =%"
if not "%OLDCP%"=="65001" chcp 65001 >nul
set "VAL="
for /f usebackq^ tokens^=1-4^ delims^=^" %%a in ("%SRC%") do (
  if "%%c"==": {" (
    set "KEY=%%b"
    call :plugin_entry
  )
  if defined INSIDE if not defined VAL if "%%b"=="engine_home" set "VAL=%%d"
)
if defined OLDCP if not "%OLDCP%"=="65001" chcp %OLDCP% >nul
if not defined VAL exit /b 0
if "%VAL%"=="," exit /b 0
set "VAL=%VAL:\\=\%"
if "%VAL:~0,1%"=="~" set "VAL=%USERPROFILE%%VAL:~1%"
set "HOME_DIR=%VAL%"
exit /b 0

:plugin_entry
rem an object key in settings.json: this plugin's entry (whynot-cut@<marketplace>) and its "options" count, others not
if "%KEY:~0,11%"=="whynot-cut@" (set "INSIDE=1") else if not "%KEY%"=="options" set "INSIDE="
exit /b 0

:default_home
set "HOME_DIR=%USERPROFILE%\.whynot-cut"
if exist "%HOME_DIR%\venv\" exit /b 0
if exist "%USERPROFILE%\.reel-editor\venv\" (set "HOME_DIR=%USERPROFILE%\.reel-editor" & exit /b 0)
if exist "%USERPROFILE%\.dr-nahla-editor\venv\" (set "HOME_DIR=%USERPROFILE%\.dr-nahla-editor" & exit /b 0)
exit /b 0

:setup
rem one build: `py -3` when the launcher exists, else the first `python` on PATH that is not a Windows Store stub
echo WhyNot Cut: no engine yet - creating it in "%HOME_DIR%" (a few minutes, ~400 MB)... 1>&2
where py >nul 2>nul
if not errorlevel 1 goto :setup_py
set "SYS_PY="
for /f "delims=" %%p in ('where python 2^>nul') do if not defined SYS_PY call :not_store "%%p"
if not defined SYS_PY exit /b 1
"%SYS_PY%" "%HERE%\setup\setup_env.py" --home "%HOME_DIR%" 1>&2
exit /b
:setup_py
py -3 "%HERE%\setup\setup_env.py" --home "%HOME_DIR%" 1>&2
exit /b
:not_store
set "CAND=%~1"
if /I not "%CAND:\WindowsApps\=%"=="%CAND%" exit /b 0
set "SYS_PY=%CAND%"
exit /b 0

:blocked
rem every blocked message names this plugin and its version, so a wrong `reel` on PATH is recognisable
set "TAG=WhyNot Cut"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%HERE%\.claude-plugin\plugin.json' | ConvertFrom-Json).version" 2^>nul`) do set "TAG=WhyNot Cut %%v"
echo {"blocked": "%TAG%: engine not installed", "how": "run: reel setup   (or /whynot-cut:start)"}
exit /b 2
