<!-- Verbatim copy of BACKLOG.md section BL-16, taken 2026-10-19 10:07. BACKLOG.md stays the source if they differ. -->
### BL-16 [Gate 4]: A safe ASCII engine home for a non-ASCII Windows user name (portability, routed by the Adobe track after R-L3)  [Gate 4 value: high]  Model: opus
- **Depends on:** none. The adobe_run space-path fix is 09d56c5.
- **Why:**
  - An Arabic Windows user name puts the engine home under `C:\Users\<name>\.whynot-cut`. Whisper's model loader and OpenCV fail on that non-ASCII path. Many editors in our market have Arabic user names.
  - Today doctor and `reel setup` suggest `setx WHYNOT_HOME C:\whynot`, a folder at the drive root. On Windows the default ACL of `C:\` lets every authenticated user **modify** files in subfolders created there. The engine home holds the Python runtime and the models, so another local account could plant code that runs as the editor.
  - `%LOCALAPPDATA%` is no answer: it sits under the same non-ASCII profile.
  - 8.3 short names are no answer for the home either: the engine resolves real paths (linksafe, `Path.resolve`), and that turns the long Arabic path back.
- **Design (executor, binding):**
  - **The suggestion:**
    - an ASCII folder on a fixed local NTFS drive: `<drive>:\WhyNotCut`;
    - prefer a non-system drive when one exists; otherwise `C:\WhyNotCut`;
    - never a network, removable or FAT/exFAT drive;
    - it holds only the engine home, never client folders.

    One function, `portability.suggested_home(drives=…)`, with injectable inputs. Every text uses it: doctor's fix, the face-model fix, setup_warnings, the ae_render StageError, platform-setup.md (as "for example").
  - **Locked on creation:** when `reel setup` creates a WHYNOT_HOME folder that is not under the user profile, it sets a protected ACL right after the exclusive create:
    - `icacls <dir> /inheritance:r /grant:r <user SID>:(OI)(CI)F *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F`;
    - use SIDs, not names (localized Windows);
    - `icacls` and `whoami` only from System32, as in a64605f;
    - a list argv with no shell.

    If the ACL step fails, setup stops with a plain Arabic-first line and the exact command for the editor. It never continues on a writable-by-others home.
  - **Checked every time:** doctor reads the home's ACL. A write, modify or full right for Everyone, Authenticated Users, Users or any SID other than the user, SYSTEM and Administrators gives a fix line, with `who: editor` and the exact icacls command. This also catches an existing `C:\whynot` made by hand.
  - **No reparse point:** the home itself and its parent must not be a junction or symlink (linksafe.is_link); otherwise refuse with a plain line.
  - **macOS:** unchanged. A non-ASCII home is fine there. The ACL check is Windows-only. POSIX checks the mode: no group or other write.
- **Owned files:**
  - `whynot-cut/engine/reel/lib/portability.py`;
  - new `whynot-cut/engine/reel/lib/home_acl.py`;
  - new `whynot-cut/tests/test_home_acl*.py`;
  - `whynot-cut/tests/test_portability.py`;
  - `whynot-cut/skills/setup/references/platform-setup.md`.
- **Must not touch:** `setup/setup_env.py`, `lib/runtime.py`, `lib/ae_render.py`, `tests/test_runtime.py`, doctor's wiring in `cli.py`. Send their hunks as patches under `hooks\BL-16\`, with their tests. The executor applies them, and the ae_render text goes through the Adobe track.
- **Done criteria:**
  - **Suggestion:** a pure function, tested with fake drive lists covering a single C:, C:+D:, D: removable, D: network, and D: FAT32.
  - **ACL:**
    - the ACL is set on create;
    - an ACL failure stops setup;
    - doctor flags the default `C:\` subfolder ACL (a parsed real `icacls` output fixture, English AND a localized Windows, read by SID);
    - a protected home passes;
    - a linked home is refused.
  - **One real Windows run on a scratch folder** (a non-system drive or `D:\ClaudeData\Temp`, never `C:\`): create, lock, read back the ACL, remove it as a folder (no link walk). No real drive root is touched by any test: the code paths take the drive root as an argument.
  - Every text names the new folder and none says `C:\whynot`. Pin this in test_portability and in the runtime patch's test.
  - An opus review PASS, and one full suite.
- **Pre-mortem first** (BRIEF rule), in `work\BL-16\premortem.md`. Check:
  - does a protected ACL break `uv`, the Whisper model download or Premiere/AE reading the engine's tmp copies? (AE runs as the same user, so it should not.)
  - Is `%ProgramData%\WhyNotCut\tmp\ae-run` from 09d56c5 still needed once the home is ASCII?
- **Fallback owner:** if no lane claims it before the API pause, the executor builds it on the subscription session.
- **Risk:** high (security + every Arabic-named editor).

