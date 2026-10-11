@echo off
rem WhyNot Cut engine wrapper for Windows PowerShell / cmd (bin\ is on PATH while the plugin is enabled).
rem Arguments reach the engine untouched: %* is expanded once, outside any ( ) block, with delayed expansion off, so
rem %, !, ^, ), $ and Arabic in arguments survive. Every path is quoted, also inside blocks. The wrapper's own
rem variables are named WNC_* and cleared before the engine starts, so none of them reaches it.
setlocal EnableExtensions DisableDelayedExpansion
set "WNC_HERE=%~dp0.."
rem Engine home, the same order as plat.engine_home(): env > the saved plugin option (the pointer file the SessionStart
rem hook writes; without a valid one, Claude Code's settings.json pluginConfigs) > %USERPROFILE%\.whynot-cut with an
rem engine (a runtime "current" file or venv\) > a legacy home (.reel-editor, .dr-nahla-editor: still read in 3.x, dropped in 4.0) > .whynot-cut.
rem The validity and entry rules match plat.saved_options() (its docstring lists the remaining edge cases).
set "WNC_HOME=%WHYNOT_HOME%"
if not defined WNC_HOME set "WNC_HOME=%CLAUDE_PLUGIN_OPTION_ENGINE_HOME%"
if not defined WNC_HOME set "WNC_HOME=%REEL_HOME%"
if not defined WNC_HOME set "WNC_HOME=%CLAUDE_PLUGIN_OPTION_REEL_HOME%"
if not defined WNC_HOME call :saved_home
if not defined WNC_HOME call :default_home
set "WHYNOT_HOME=%WNC_HOME%"
rem The engine interpreter (3.0 T2.1, same order as plat.engine_runtime()): the isolated runtime named by the one-line
rem text file <home>\current (runtimes\<id>\, run with -s: no user site), else the 2.x venv\ (run as before). Never a
rem system Python for the engine; `reel setup` with neither builds the runtime first.
call :find_py
if not defined WNC_PY if /I "%~1"=="setup" call :setup
if defined WNC_NOPY goto :no_python
if not defined WNC_PY call :find_py
if not defined WNC_PY if defined WNC_SETUP_RAN goto :setup_failed
if not defined WNC_PY goto :blocked
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
rem the whole line is expanded before it runs, so the WNC_* values are used and already cleared for the engine
set "WNC_HOME=" & set "WNC_PY=" & set "WNC_HERE=" & set "WNC_FLAG=" & set "WNC_SETUP_RAN=" & "%WNC_PY%" %WNC_FLAG% "%WNC_HERE%\engine\reel\cli.py" %*
exit /b %ERRORLEVEL%

:find_py
rem WNC_PY (+ WNC_FLAG=-s for a runtime). <home>\current holds one runtime id, the rule of lib/plat.py:
rem [A-Za-z0-9] then up to 79 of [A-Za-z0-9._-], no ".."; anything else falls back to venv\ (as doctor reports it)
rem (%WNC_RT:x=y% is expanded when its line is read, also behind a false `if`: so every line that uses it is
rem reached only by goto once WNC_RT is defined)
set "WNC_PY="
set "WNC_FLAG="
set "WNC_RT="
if exist "%WNC_HOME%\current" set /p WNC_RT=<"%WNC_HOME%\current"
if not defined WNC_RT goto :find_venv
set "WNC_RT=%WNC_RT:"=%"
if not defined WNC_RT goto :find_venv
set "WNC_RT=%WNC_RT: =%"
if not defined WNC_RT goto :find_venv
if not "%WNC_RT:\=%"=="%WNC_RT%" goto :find_venv
if not "%WNC_RT:/=%"=="%WNC_RT%" goto :find_venv
if not "%WNC_RT::=%"=="%WNC_RT%" goto :find_venv
if not "%WNC_RT:..=%"=="%WNC_RT%" goto :find_venv
if not "%WNC_RT:~80%"=="" goto :find_venv
for %%c in (. - _) do if "%WNC_RT:~0,1%"=="%%c" goto :find_venv
rem every allowed character is a delimiter: any token left is a character outside the rule ("x" keeps the line from
rem starting with the eol character)
for /f "eol=| delims=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" %%x in ("x%WNC_RT%") do goto :find_venv
if not exist "%WNC_HOME%\runtimes\%WNC_RT%\Scripts\python.exe" goto :find_venv
set "WNC_PY=%WNC_HOME%\runtimes\%WNC_RT%\Scripts\python.exe"
set "WNC_FLAG=-s"
set "WNC_RT="
exit /b 0
:find_venv
set "WNC_RT="
if exist "%WNC_HOME%\venv\Scripts\python.exe" set "WNC_PY=%WNC_HOME%\venv\Scripts\python.exe"
exit /b 0

:saved_home
rem engine_home from the pointer file when it is valid (an "engine_home" string line and the closing brace; "" = not
rem set), else from settings.json. Both are read as JSON with one key per line, as UTF-8 (chcp 65001, put back after)
rem so an Arabic path survives.
set "WNC_PTR=%WHYNOT_OPTIONS_FILE%"
if not defined WNC_PTR set "WNC_PTR=%USERPROFILE%\.whynot-cut\plugin-options.json"
set "WNC_CFG=%CLAUDE_CONFIG_DIR%"
if not defined WNC_CFG set "WNC_CFG=%USERPROFILE%\.claude"
set "WNC_CFG=%WNC_CFG%\settings.json"
if not exist "%WNC_PTR%" if not exist "%WNC_CFG%" goto :saved_done
set "WNC_OLDCP="
for /f "tokens=2 delims=:." %%c in ('chcp') do set "WNC_OLDCP=%%c"
if defined WNC_OLDCP set "WNC_OLDCP=%WNC_OLDCP: =%"
if not "%WNC_OLDCP%"=="65001" chcp 65001 >nul
call :scan_reset
if exist "%WNC_PTR%" (
  set "WNC_SRC=%WNC_PTR%"
  set "WNC_IN_ID=1"
  set "WNC_SEEN_ID=1"
  call :scan
)
if defined WNC_GOT_ID if defined WNC_CLOSED goto :saved_pick
call :scan_reset
if exist "%WNC_CFG%" (
  set "WNC_SRC=%WNC_CFG%"
  call :scan
)
:saved_pick
if defined WNC_OLDCP if not "%WNC_OLDCP%"=="65001" chcp %WNC_OLDCP% >nul
set "WNC_VAL="
if defined WNC_SEEN_ID (set "WNC_VAL=%WNC_VAL_ID%") else if defined WNC_SEEN_ANY set "WNC_VAL=%WNC_VAL_ANY%"
if "%WNC_VAL%"=="," set "WNC_VAL="
if not defined WNC_VAL goto :saved_done
set "WNC_VAL=%WNC_VAL:\\=\%"
if "%WNC_VAL:~0,1%"=="~" set "WNC_VAL=%USERPROFILE%%WNC_VAL:~1%"
set "WNC_HOME=%WNC_VAL%"
:saved_done
call :scan_reset
set "WNC_PTR=" & set "WNC_CFG=" & set "WNC_OLDCP=" & set "WNC_VAL="
exit /b 0

:scan
rem one key per line, split on the double quote: %%b = key, %%c = ": " before a string value or ": {" before an
rem object, %%d = the string value ("," when it is empty). pluginConfigs entry whynot-cut@thewhynot-ai when it has
rem "options", else the first other whynot-cut@* entry that has them.
for /f usebackq^ tokens^=1-4^ delims^=^" %%a in ("%WNC_SRC%") do (
  if "%%c"==": {" (
    set "WNC_KEY=%%b"
    call :plugin_entry
  )
  if "%%b"=="engine_home" if "%%c"==": " if defined WNC_IN_ID if defined WNC_SEEN_ID if not defined WNC_GOT_ID (
    set "WNC_VAL_ID=%%d"
    set "WNC_GOT_ID=1"
  )
  if "%%b"=="engine_home" if "%%c"==": " if defined WNC_IN_ANY if defined WNC_SEEN_ANY if not defined WNC_GOT_ANY (
    set "WNC_VAL_ANY=%%d"
    set "WNC_GOT_ANY=1"
  )
  if "%%a"=="}" set "WNC_CLOSED=1"
)
exit /b 0

:plugin_entry
if "%WNC_KEY%"=="options" (
  if defined WNC_IN_ID set "WNC_SEEN_ID=1"
  if defined WNC_IN_ANY set "WNC_SEEN_ANY=1"
  exit /b 0
)
set "WNC_IN_ID="
set "WNC_IN_ANY="
if "%WNC_KEY%"=="whynot-cut@thewhynot-ai" (
  set "WNC_IN_ID=1"
  exit /b 0
)
if not defined WNC_SEEN_ANY if "%WNC_KEY:~0,11%"=="whynot-cut@" set "WNC_IN_ANY=1"
exit /b 0

:scan_reset
for %%v in (SRC KEY IN_ID IN_ANY SEEN_ID SEEN_ANY GOT_ID GOT_ANY VAL_ID VAL_ANY CLOSED) do set "WNC_%%v="
exit /b 0

:default_home
set "WNC_HOME=%USERPROFILE%\.whynot-cut"
if exist "%WNC_HOME%\venv\" exit /b 0
if exist "%WNC_HOME%\current" exit /b 0
if exist "%USERPROFILE%\.reel-editor\venv\" (
  set "WNC_HOME=%USERPROFILE%\.reel-editor"
  exit /b 0
)
if exist "%USERPROFILE%\.dr-nahla-editor\venv\" set "WNC_HOME=%USERPROFILE%\.dr-nahla-editor"
exit /b 0

:setup
rem one build: `py -3` when the launcher exists, else the first `python` on PATH that is not a Windows Store stub
rem (where's output is filtered by findstr, so no path goes through a second `call` expansion); none: WNC_NOPY
echo WhyNot Cut: no engine yet - creating it in "%WNC_HOME%" (a few minutes, ~400 MB)... 1>&2
where py >nul 2>nul
if not errorlevel 1 goto :setup_py
set "WNC_SYS_PY="
for /f "delims=" %%p in ('where python 2^>nul ^| findstr /v /i /l /c:"\WindowsApps\\"') do if not defined WNC_SYS_PY set "WNC_SYS_PY=%%p"
if not defined WNC_SYS_PY (
  set "WNC_NOPY=1"
  exit /b 1
)
set "WNC_SETUP_RAN=1"
"%WNC_SYS_PY%" "%WNC_HERE%\setup\setup_env.py" --home "%WNC_HOME%" 1>&2
set "WNC_SYS_PY="
exit /b
:setup_py
set "WNC_SETUP_RAN=1"
py -3 "%WNC_HERE%\setup\setup_env.py" --home "%WNC_HOME%" 1>&2
exit /b

:tag
rem every blocked message names this plugin and its version, so a wrong `reel` on PATH is recognisable
set "WNC_TAG=WhyNot Cut"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content -Raw -LiteralPath '%WNC_HERE%\.claude-plugin\plugin.json' | ConvertFrom-Json).version" 2^>nul`) do set "WNC_TAG=WhyNot Cut %%v"
exit /b 0

:no_python
call :tag
echo {"blocked": "%WNC_TAG%: no Python 3.9+ found to build the engine", "how": "Windows: winget install Python.Python.3.12 - then run: reel setup"}
exit /b 2

:setup_failed
call :tag
echo {"blocked": "%WNC_TAG%: building the engine runtime failed (its report is above)", "how": "check the internet connection, then run: reel setup"}
exit /b 2

:blocked
call :tag
echo {"blocked": "%WNC_TAG%: engine not installed", "how": "run: reel setup   (or /whynot-cut:start)"}
exit /b 2
