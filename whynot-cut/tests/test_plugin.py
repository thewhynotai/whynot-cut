"""Plugin-level tests: hooks (guardrails), client profiles, bridge script sync, CLI gates.
Run:  ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402

GUARD = SK / "hooks" / "guard.py"
CTX = SK / "hooks" / "session_context.py"


CLIENTS_ENV = ("WHYNOT_CLIENTS_ROOT", "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT")
NO_CLIENTS_ROOT = str(Path(tempfile.gettempdir()) / "whynot-test-clients-root-unset")
MARKER = ".whynot-client"


def isolated_env(env=None) -> dict:
    """Hook environment that never reads the real user's clients_root (an explicit, empty one unless the test sets
    its own) and has no plugin data folder unless the test gives one."""
    out = {k: v for k, v in os.environ.items() if k not in CLIENTS_ENV and k != "CLAUDE_PLUGIN_DATA"}
    env = dict(env or {})
    if not any(k in env for k in CLIENTS_ENV):
        env["WHYNOT_CLIENTS_ROOT"] = NO_CLIENTS_ROOT
    out.update(env)
    return out


def mark_client(root: Path) -> Path:
    """Client folders are recognised by a positive marker (3.0); test fixtures create it like `reel scaffold` does."""
    (root / MARKER).write_text('{"whynot_client": 1, "created": "test"}', encoding="utf-8")
    return root


def hook(script, payload, env=None):
    r = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), capture_output=True, text=True,
                       encoding="utf-8", env=isolated_env(env))
    return r.returncode, r.stdout, r.stderr


class ClientFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "example clinic"
        for d in ("assets/Photos", "data/Raw", "output/projects/C0001"):
            (self.root / d).mkdir(parents=True)
        (self.root / "data/Raw/C0001.MP4").write_bytes(b"x")
        mark_client(self.root)

    def tearDown(self):
        self.tmp.cleanup()
        common.set_context(None, None)


class TestGuardProtected(ClientFixture):
    def bash(self, cmd, agent=None):
        p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def test_write_edit_blocked_in_sources(self):
        for tool in ("Write", "Edit"):
            code, _, err = hook(GUARD, {"tool_name": tool, "cwd": "/", "tool_input": {"file_path": str(self.root / "data/Raw/new.txt")}})
            self.assertEqual(code, 2, tool)
            self.assertIn("read-only", err)
        code, _, _ = hook(GUARD, {"tool_name": "Write", "cwd": "/", "tool_input": {"file_path": str(self.root / "output/x.json")}})
        self.assertEqual(code, 0)

    def test_bash_mutations_blocked(self):
        blocked = ['rm "data/Raw/C0001.MP4"', "mv assets/Photos/a.jpg /tmp/", "echo hi > data/Raw/note.txt",
                   "cp /tmp/a.png assets/Photos/", "sed -i '' s/a/b/ data/Raw/x.srt", "touch assets/x",
                   f"ffmpeg -i in.mp4 -y '{self.root}/data/Raw/out.mp4'", "rm -rf output/projects/C0001", "rm -rf output"]
        for c in blocked:
            self.assertEqual(self.bash(c), 2, c)

    def test_bash_reads_allowed(self):
        ok = ["ls data/Raw", f"ffmpeg -i '{self.root}/data/Raw/C0001.MP4' -y output/projects/C0001/a.wav",
              "cp data/Raw/C0001.MP4 /tmp/copy.mp4", "rm output/projects/C0001/tmp.json", "cat assets/Photos/x | head",
              "reel next --root .", "grep -r teal assets"]
        for c in ok:
            self.assertEqual(self.bash(c), 0, c)

    def test_bash_destination_forms(self):
        """Destinations that are not the last argument: cp -t, trailing ffmpeg options, find -delete/-exec."""
        blocked = ["cp -t data/Raw /tmp/a.png", "cp --target-directory=assets/Photos /tmp/a.png",
                   "ffmpeg -i in.mp4 data/Raw/out.mp4 -loglevel error", "ffmpeg -i in.mp4 -progress data/Raw/p.txt out.mp4",
                   "find data -name '*.MP4' -delete", "find assets -exec rm {} +", "find . -name '*.tmp' -delete",
                   "find output -fprint data/Raw/list.txt"]
        for c in blocked:
            self.assertEqual(self.bash(c), 2, c)
        ok = ["cp -t output/projects/C0001 data/Raw/C0001.MP4", "find data -name '*.MP4'",
              "find output -name '*.tmp' -delete", "find data -exec ls -l {} +",
              "ffmpeg -hide_banner -i data/Raw/C0001.MP4 -vf subtitles=data/Raw/x.srt output/projects/C0001/a.mp4 -loglevel error"]
        for c in ok:
            self.assertEqual(self.bash(c), 0, c)

    def test_cd_in_chain_is_followed(self):
        """`cd <client> && rm data/x` from a non-client folder must be blocked (relative to the cd target)."""
        outside = Path(self.tmp.name)
        p = {"tool_name": "Bash", "tool_input": {"command": f'cd "{self.root}" && rm data/Raw/C0001.MP4'}, "cwd": str(outside)}
        self.assertEqual(hook(GUARD, p)[0], 2)
        p = {"tool_name": "Bash", "tool_input": {"command": f'cd "{outside}" && rm assets/x.txt'}, "cwd": str(self.root)}
        self.assertEqual(hook(GUARD, p)[0], 0)          # assets/ here means <outside>/assets, not the client's
        p = {"tool_name": "Bash", "tool_input": {"command": "cd data/Raw && rm C0001.MP4"}, "cwd": str(self.root)}
        self.assertEqual(hook(GUARD, p)[0], 2)

    def test_multiline_and_heredoc(self):
        """Each line is a command (no gluing); heredoc bodies are data, not commands."""
        self.assertEqual(self.bash("ls\nrm data/Raw/C0001.MP4"), 2)
        body = "python3 - <<'EOF'\nprint('rm data/Raw/C0001.MP4')\nrm data/Raw/C0001.MP4\nEOF\necho done"
        self.assertEqual(self.bash(body), 0)
        self.assertEqual(self.bash("cat <<EOF > notes.txt\nhello\nEOF\nmv data/Raw/C0001.MP4 /tmp/"), 2)

    def test_extras_and_roles(self):
        self.assertEqual(self.bash("reel ae-build --root ."), 2)
        self.assertEqual(self.bash("reel ae-build --root . --extras"), 0)
        self.assertEqual(self.bash("reel ppro-build --root ."), 0)
        self.assertEqual(self.bash("reel approve-plan --by editor", agent="whynot-cut:story-editor"), 2)
        self.assertEqual(self.bash("reel approve-plan --by editor"), 0)          # lead (no agent_type)
        self.assertEqual(self.bash("reel verify --record --verdict pass --notes x", agent="whynot-cut:qc-reviewer"), 2)
        self.assertEqual(self.bash("reel ppro-build --force", agent="whynot-cut:qc-reviewer"), 2)
        self.assertEqual(self.bash("reel qc", agent="whynot-cut:qc-reviewer"), 0)
        self.assertEqual(self.bash("reel ppro-frames", agent="whynot-cut:qc-reviewer"), 0)
        code, _, _ = hook(GUARD, {"tool_name": "Write", "agent_type": "whynot-cut:medical-reviewer", "cwd": "/",
                                  "tool_input": {"file_path": str(self.root / "output/a.md")}})
        self.assertEqual(code, 2)

    def test_session_context(self):
        code, out, _ = hook(CTX, {"cwd": str(self.root)})
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Profile: NONE", ctx)                # a shipped profile is never matched by folder name
        self.assertNotIn("example-clinic", ctx)
        code, out, _ = hook(CTX, {"cwd": tempfile.gettempdir()})
        self.assertEqual(out.strip(), "")                  # silent outside client folders

    def test_clients_root_setting(self):
        """clients_root (plugin setting): SessionStart lists the clients there; --root takes a bare client name."""
        base = str(self.root.parent)
        env = {"CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT": base}
        code, out, _ = hook(CTX, {"cwd": base}, env)
        self.assertIn("example clinic", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        code, out, _ = hook(CTX, {"cwd": base})
        self.assertEqual(out.strip(), "")                  # unset: still silent
        r = subprocess.run([sys.executable, str(SK / "engine/reel/cli.py"), "--root", "example clinic", "profile"],
                           capture_output=True, text=True, cwd=tempfile.gettempdir(), env=dict(os.environ, **env))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(json.loads(r.stdout)["active"])      # no folder-name match for shipped profiles
        self.assertIn("example-clinic", json.loads(r.stdout)["shipped_profiles"])


def find_bash():
    """Git Bash on Windows (never WSL's System32 bash), the system bash elsewhere."""
    import shutil
    return next((b for b in (os.environ.get("GIT_BASH"), r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash"))
                 if b and Path(b).exists() and "system32" not in b.lower()), None)


class TestClientMarker(unittest.TestCase):
    """T1.5 / structure 4.1: a folder is a client folder only with a positive marker — `.whynot-client`, an
    `output/client_database/`, or lying under clients_root. A Hugo site (assets/ + data/) is left alone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def site(self, name="HugoSite", parent=None) -> Path:
        root = (parent or self.base) / name
        for d in ("assets/css", "data", "content"):
            (root / d).mkdir(parents=True)
        (root / "assets/css/main.scss").write_text("body{}", encoding="utf-8")
        (root / "data/site.yaml").write_text("title: x", encoding="utf-8")
        return root

    def write(self, path, env=None):
        return hook(GUARD, {"tool_name": "Write", "cwd": str(self.base),
                            "tool_input": {"file_path": str(path), "content": "x"}}, env)[0]

    def cmd(self, tool, command, cwd, env=None):
        return hook(GUARD, {"tool_name": tool, "cwd": str(cwd), "tool_input": {"command": command}}, env)[0]

    def test_hugo_site_is_not_blocked_and_gets_no_context(self):
        root = self.site()
        self.assertEqual(self.write(root / "data/site.yaml"), 0)
        self.assertEqual(hook(GUARD, {"tool_name": "Edit", "cwd": str(root),
                                      "tool_input": {"file_path": str(root / "assets/css/main.scss")}})[0], 0)
        self.assertEqual(self.cmd("Bash", "rm data/site.yaml", root), 0)
        self.assertEqual(self.cmd("Bash", "find assets -name '*.scss' -delete", root), 0)
        self.assertEqual(self.cmd("PowerShell", "Remove-Item data/site.yaml", root), 0)
        code, out, _ = hook(CTX, {"cwd": str(root)})
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")                       # no "this is a client folder"

    def test_marker_makes_a_client(self):
        root = mark_client(self.site("Dr Marker"))
        self.assertEqual(self.write(root / "data/site.yaml"), 2)
        self.assertEqual(self.cmd("Bash", "rm data/site.yaml", root), 2)
        code, out, _ = hook(CTX, {"cwd": str(root)})
        self.assertIn("this is a client folder", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_client_database_makes_a_client(self):
        root = self.site("Dr Legacy")
        (root / "output/client_database").mkdir(parents=True)
        self.assertEqual(self.write(root / "assets/css/main.scss"), 2)

    def test_under_clients_root_is_a_client(self):
        clients = self.base / "Clients"
        root = self.site("Dr Under", clients)
        env = {"WHYNOT_CLIENTS_ROOT": str(clients)}
        self.assertEqual(self.write(root / "data/site.yaml", env), 2)
        self.assertEqual(self.cmd("Bash", "rm data/site.yaml", root, env), 2)
        outside = self.site("HugoSite")
        self.assertEqual(self.write(outside / "data/site.yaml", env), 0)
        code, out, _ = hook(CTX, {"cwd": str(root)}, env)
        self.assertIn("this is a client folder", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_clients_root_from_the_preferences_file(self):
        from unittest import mock
        sys.path.insert(0, str(SK / "engine/reel"))
        from lib import client_marker
        ws = self.base / "ws"
        (ws / ".claude").mkdir(parents=True)
        (ws / ".claude/whynot-cut.local.md").write_text(f'---\nclients_root: "{ws.as_posix()}"\n---\n', encoding="utf-8")
        root = self.site("Dr Prefs", ws)
        with mock.patch.dict(os.environ, {k: "" for k in CLIENTS_ENV}):   # the walk stops at ws/.claude
            self.assertEqual(client_marker.clients_base(root).resolve(), ws.resolve())
            self.assertTrue(client_marker.is_client(root))

    def test_scaffold_writes_the_marker(self):
        from lib.onboard import scaffold
        root = self.base / "Dr New"
        self.assertEqual(scaffold(root, "Dr New")["status"], "CREATED")
        m = json.loads((root / MARKER).read_text(encoding="utf-8"))
        self.assertEqual(m["whynot_client"], 1)
        self.assertTrue(m["created"])
        self.assertFalse(list((root / "assets").rglob(MARKER)) + list((root / "data").rglob(MARKER)))

    def test_client_init_writes_the_marker(self):
        root = self.site("Dr Init")
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(root), "client-init",
                            "--id", "dr-init"], capture_output=True, text=True, encoding="utf-8", env=isolated_env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((root / MARKER).read_text(encoding="utf-8"))["whynot_client"], 1)

    def test_doctor_fix_marks_an_existing_client(self):
        root = self.site("Dr Old")
        cfg = self.base / "cfg"
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(root), "doctor", "--fix"],
                           capture_output=True, text=True, encoding="utf-8",
                           env=isolated_env({"CLAUDE_CONFIG_DIR": str(cfg)}))
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        self.assertTrue((root / MARKER).is_file())
        self.assertIn(str(root / MARKER), [str(Path(p)) for p in rep["client_markers"]["written"]])
        self.assertFalse((root / "assets" / MARKER).exists() or (root / "data" / MARKER).exists())

    def test_marker_never_goes_into_sources(self):
        from lib import client_marker
        root = mark_client(self.site("Dr Src"))
        for bad in (root / "data", root / "assets/css"):
            with self.assertRaises(ValueError):
                client_marker.write_marker(bad)


class TestGuardBypasses(ClientFixture):
    """T1.5 / structure 4.5, engine IM-17: each bypass found by the review is blocked when it targets client sources."""

    def run_tool(self, tool, cmd, agent=None):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def bash(self, cmd, agent=None):
        return self.run_tool("Bash", cmd, agent)

    def ps(self, cmd, agent=None):
        return self.run_tool("PowerShell", cmd, agent)

    def test_powershell_pipeline_into_a_mutator(self):
        for c in ["Get-ChildItem data/Raw | Remove-Item",
                  "Get-ChildItem -Path data/Raw -Filter *.MP4 | ForEach-Object { Remove-Item $_.FullName }",
                  "gci assets -Recurse | ri -Force", "ls data/Raw | Move-Item -Destination output/",
                  "Get-ChildItem data | % { $_.Delete() }", "Get-ChildItem data/Raw | Set-Content -Value x"]:
            self.assertEqual(self.ps(c), 2, c)
        for c in ["Get-ChildItem data/Raw | Select-Object Name", "Get-ChildItem output | Remove-Item",
                  "Get-Content data/Raw/x.srt | Out-File output/x.srt",
                  "Get-Content data/Raw/x.srt | Set-Content -Path output/x.srt",
                  "Get-ChildItem data/Raw; Get-ChildItem output | Remove-Item"]:
            self.assertEqual(self.ps(c), 0, c)

    def test_xargs_mutator(self):
        for c in ["ls data/Raw/*.MP4 | xargs rm", "find data -name '*.MP4' -print0 | xargs -0 rm -f",
                  "xargs rm < list.txt data/Raw/C0001.MP4", "cd data/Raw && ls | xargs rm"]:
            self.assertEqual(self.bash(c), 2, c)
        for c in ["ls output | xargs rm", "ls data/Raw | xargs -I{} cp data/Raw/{} output/", "ls data/Raw | xargs echo"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_command_substitution_bodies(self):
        for c in ["echo $(rm data/Raw/C0001.MP4)", "echo `rm data/Raw/C0001.MP4`",
                  'x="$(mv data/Raw/C0001.MP4 /tmp/)"', "echo $(echo $(rm data/Raw/C0001.MP4))",
                  "(rm data/Raw/C0001.MP4)", "if true; then rm data/Raw/C0001.MP4; fi"]:
            self.assertEqual(self.bash(c), 2, c)
        for c in ["echo '$(rm data/Raw/C0001.MP4)'", "echo $(ls data/Raw)", "n=$(wc -l < data/Raw/C0001.MP4)"]:
            self.assertEqual(self.bash(c), 0, c)
        self.assertEqual(self.ps("Write-Output $(Remove-Item data/Raw/C0001.MP4)"), 2)

    def test_dotnet_file_calls(self):
        for c in ['[IO.File]::Delete("data/Raw/C0001.MP4")', "[System.IO.File]::WriteAllText('data/Raw/n.txt', 'x')",
                  '[System.IO.File]::Move("data/Raw/C0001.MP4", "output/a.mp4")',
                  '[IO.File]::Copy("output/a.mp4", "assets/Photos/a.mp4")', "[IO.Directory]::Delete('data', $true)"]:
            self.assertEqual(self.ps(c), 2, c)
        self.assertEqual(self.bash("""powershell -Command "[IO.File]::Delete('data/Raw/C0001.MP4')" """), 2)
        for c in ['[IO.File]::ReadAllText("data/Raw/x.srt")', '[IO.File]::Copy("data/Raw/C0001.MP4", "output/a.mp4")',
                  '[IO.File]::Delete("output/a.mp4")']:
            self.assertEqual(self.ps(c), 0, c)

    def test_git_on_sources(self):
        for c in ["git -C data checkout -- .", "git -C data/Raw clean -fdx", "git checkout -- data/Raw/C0001.MP4",
                  "git rm data/Raw/C0001.MP4", "git mv data/Raw/C0001.MP4 output/", "git -C data reset --hard",
                  "git restore data/Raw", "git clean -fdx"]:
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.ps("git -C data checkout -- ."), 2)
        for c in ["git status", "git -C data log --oneline", "git diff data/Raw", "git checkout main",
                  "git add output/x.json", "git -C output clean -fd"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_adobe_prefs_through_wrappers(self):
        import base64
        key = r"HKCU\Software\Adobe\CSXS.12"
        enc = base64.b64encode(f"Set-ItemProperty -Path 'HKCU:\\Software\\Adobe\\CSXS.12' -Name PlayerDebugMode -Value 1"
                               .encode("utf-16-le")).decode()
        for c in [f'cmd /c reg add "{key}" /v PlayerDebugMode /t REG_SZ /d 1 /f',
                  f'cmd.exe /c "reg add {key} /v PlayerDebugMode /d 1 /f"',
                  f'''powershell -Command "Set-ItemProperty -Path 'HKCU:\\Software\\Adobe\\CSXS.12' -Name PlayerDebugMode -Value 1"''',
                  f'''powershell.exe -NoProfile -ExecutionPolicy Bypass -c "New-ItemProperty -Path 'HKCU:\\Software\\Adobe\\CSXS.11' -Name PlayerDebugMode -Value 1"''',
                  f"pwsh -EncodedCommand {enc}", 'bash -c "rm data/Raw/C0001.MP4"']:
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.ps(f"cmd /c reg add {key} /v PlayerDebugMode /d 1 /f"), 2)
        for c in [f'cmd /c reg query "{key}"',
                  '''powershell -Command "Get-ItemProperty -Path 'HKCU:\\Software\\Adobe\\CSXS.12'"''',
                  'cmd /c dir data', 'bash -c "ls data/Raw"']:
            self.assertEqual(self.bash(c), 0, c)


class TestGuardRoles(ClientFixture):
    """T1.5 / engine §10 role holes and structure 4.7 (role rules key on the full whynot-cut:<name>)."""

    def bash(self, cmd, agent=None):
        p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def test_subagents_cannot_verify_as_the_editor(self):
        for c in ["reel transcript-verify --video-id C0001 --by editor", "reel transcript-verify --by=editor"]:
            self.assertEqual(self.bash(c, "whynot-cut:transcript-editor"), 2, c)
            self.assertEqual(self.bash(c), 0, c)                                    # the lead may
        self.assertEqual(self.bash("reel transcript-verify --video-id C0001 --by transcript-editor",
                                   "whynot-cut:transcript-editor"), 0)

    def test_qc_reviewer_cannot_run_ref_analyze(self):
        self.assertEqual(self.bash("reel ref-analyze --root .", "whynot-cut:qc-reviewer"), 2)
        self.assertEqual(self.bash("reel ref-analyze --root .", "whynot-cut:client-researcher"), 0)

    def test_setup_doctor_cannot_run_setup(self):
        self.assertEqual(self.bash("reel setup", "whynot-cut:setup-doctor"), 2)
        self.assertEqual(self.bash("reel doctor --fix", "whynot-cut:setup-doctor"), 2)
        self.assertEqual(self.bash("reel doctor", "whynot-cut:setup-doctor"), 0)
        self.assertEqual(self.bash("reel setup"), 0)

    def test_roles_match_the_full_agent_type(self):
        for other in ("other-plugin:qc-reviewer", "qc-reviewer"):
            self.assertEqual(self.bash("reel ppro-build --force", other), 0, other)
            code = hook(GUARD, {"tool_name": "Write", "agent_type": other.replace("qc-reviewer", "medical-reviewer"),
                                "cwd": "/", "tool_input": {"file_path": str(self.root / "output/a.md")}})[0]
            self.assertEqual(code, 0, other)
        self.assertEqual(self.bash("reel ppro-build --force", "whynot-cut:qc-reviewer"), 2)
        # gate rules bind every subagent, whatever plugin it comes from
        self.assertEqual(self.bash("reel approve-plan --by editor", "other-plugin:helper"), 2)


class TestHookRunner(unittest.TestCase):
    """T1.5 / structure 4.2, 4.3, engine IM-17: run_python.sh picks the engine runtime first, skips the Windows Store
    stub, caches its pick in ${CLAUDE_PLUGIN_DATA}/python, writes a heartbeat, and is never silently off."""

    def setUp(self):
        self.bash_exe = find_bash()
        if not self.bash_exe:
            self.skipTest("no bash")
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.data = self.t / "plugin-data"
        self.home = self.t / "home"
        self.home.mkdir()
        self.data.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, path: Path, word: str) -> Path:
        """A stand-in interpreter that refuses `-c` (so a separate version probe would reject it) and echoes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!/bin/sh\ncase "$1" in -c) exit 1;; esac\necho {word} "$@"\n', encoding="utf-8", newline="\n")
        path.chmod(0o755)
        return path

    def run_hook(self, script="guard.py", path_dirs=(), engine_home=None):
        sysdirs = [str(Path(self.bash_exe).parent.parent / "usr/bin")] if os.name == "nt" else []
        env = isolated_env({"PATH": os.pathsep.join([str(d) for d in path_dirs] + sysdirs),
                            "HOME": str(self.home), "WHYNOT_HOME": str(engine_home or self.t / "no-engine"),
                            "CLAUDE_PLUGIN_DATA": str(self.data), "CLAUDE_PLUGIN_ROOT": str(SK)})
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(self.t)})
        return subprocess.run([self.bash_exe, str(SK / "hooks/run_python.sh"), str(SK / "hooks" / script)], input=payload,
                              capture_output=True, text=True, encoding="utf-8", env=env)

    def test_engine_runtime_first(self):
        eng = self.t / "engine"
        self.fake(eng / "venv/Scripts/python.exe", "ENGINE")
        self.fake(eng / "venv/bin/python", "ENGINE")
        self.fake(self.t / "bin/python3", "SYSTEM")
        r = self.run_hook(path_dirs=[self.t / "bin"], engine_home=eng)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("ENGINE"), r.stdout)
        self.assertIn("guard.py", r.stdout)

    def test_store_stub_skipped_pick_cached_and_heartbeat(self):
        self.fake(self.t / "WindowsApps/python3", "STUB")
        real = self.fake(self.t / "bin/python3", "REAL")
        r = self.run_hook(path_dirs=[self.t / "WindowsApps", self.t / "bin"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("REAL"), r.stdout)          # no separate version probe either
        cached = (self.data / "python").read_text(encoding="utf-8").strip()
        self.assertTrue(cached.replace("\\", "/").endswith("bin/python3"), cached)
        hb = self.data / "hooks-ok"
        self.assertTrue(hb.is_file())
        import time
        self.assertLess(time.time() - hb.stat().st_mtime, 60)
        # the cached pick is used even when PATH no longer has it
        r = self.run_hook(path_dirs=[self.t / "WindowsApps"])
        self.assertTrue(r.stdout.startswith("REAL"), (r.stdout, r.stderr))
        # a cached interpreter that disappeared is re-resolved (here: nothing left -> visible, not silent)
        real.unlink()
        hb.unlink()
        r = self.run_hook(path_dirs=[self.t / "WindowsApps"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("no Python", r.stderr)
        self.assertFalse(hb.exists())                                   # no heartbeat without a run

    def test_no_python_is_visible_at_session_start(self):
        r = self.run_hook("session_context.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "SessionStart")
        self.assertEqual(ctx["additionalContext"], "WhyNot Cut protection is OFF: no Python found — run reel doctor")


class TestHeartbeat(ClientFixture):
    """session_context warns when the hooks heartbeat is missing or stale; doctor reports guard_active."""

    def ctx(self, data: Path):
        code, out, _ = hook(CTX, {"cwd": str(self.root)}, {"CLAUDE_PLUGIN_DATA": str(data)})
        self.assertEqual(code, 0)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_session_context_warns_without_a_fresh_heartbeat(self):
        import time
        data = Path(self.tmp.name) / "pdata"
        data.mkdir()
        self.assertIn("protection may be OFF", self.ctx(data))           # missing
        hb = data / "hooks-ok"
        hb.write_text("1", encoding="utf-8")
        self.assertNotIn("protection may be OFF", self.ctx(data))        # fresh
        old = time.time() - 3 * 86400
        os.utime(hb, (old, old))
        self.assertIn("protection may be OFF", self.ctx(data))           # stale

    def test_doctor_guard_active(self):
        import time
        from unittest import mock
        from lib import onboard
        cfg = Path(self.tmp.name) / "cfg"
        env = {"CLAUDE_CONFIG_DIR": str(cfg), "CLAUDE_PLUGIN_DATA": ""}
        with mock.patch.dict(os.environ, env):
            st = onboard.guard_heartbeat()
            self.assertFalse(st["active"])
            self.assertIn("Git for Windows" if os.name == "nt" else "restart Claude Code", st["fix"])
            hb = cfg / "plugins/data/whynot-cut-thewhynot-ai/hooks-ok"
            hb.parent.mkdir(parents=True)
            hb.write_text("1", encoding="utf-8")
            st = onboard.guard_heartbeat()
            self.assertTrue(st["active"])
            self.assertEqual(Path(st["file"]), hb)
            old = time.time() - 2 * 86400
            os.utime(hb, (old, old))
            self.assertFalse(onboard.guard_heartbeat()["active"])
            rep = onboard.doctor()
        self.assertIs(rep["guard_active"], False)
        self.assertTrue(any("guard" in f["item"].lower() for f in rep["fixes"]), rep["fixes"])


class TestProfiles(ClientFixture):
    def test_shipped_profile_only_by_name_and_merge(self):
        common.set_context(self.root)                                  # folder "example clinic": NOT matched by name
        self.assertIsNone(common.active_profile())
        self.assertEqual(common.project_prefix(), "RE")
        common.set_context(self.root, "example-clinic")                # applied only when named (--profile)
        self.assertEqual(common.active_profile(), "example-clinic")
        self.assertEqual(common.project_prefix(), "EC")
        self.assertEqual(common.brand_fallback("primary"), "#2A7FBA")
        self.assertIn("سامبل", common.load_config("transcription.json")["initial_prompt"])
        self.assertEqual(common.load_config("sequence-settings.json")["general"]["timebase"], 24)

    def test_no_shipped_profile_declares_a_folder_match(self):
        """The folder-name auto-match is gone: no shipped profile or default carries `match` rules any more."""
        for d in (common.PROFILES_DIR / "_template", common.CONFIG_DIR):
            self.assertNotIn("match", json.loads((d / "profile.json").read_text(encoding="utf-8")), d)
        for pid, pj in common.shipped_profiles().items():
            self.assertNotIn("match", pj, pid)

    def test_old_match_rules_in_a_profile_are_ignored(self):
        """A profile that still carries `match.folder_contains` (older copies) does not auto-apply to a folder."""
        from unittest import mock
        shipped = Path(self.tmp.name) / "shipped"
        (shipped / "old-seed").mkdir(parents=True)
        (shipped / "old-seed/profile.json").write_text(
            json.dumps({"id": "old-seed", "prefix": "OS", "match": {"folder_contains": ["example"]}}), encoding="utf-8")
        with mock.patch.object(common, "PROFILES_DIR", shipped):
            common.set_context(self.root)                              # folder name contains "example"
            self.assertIsNone(common.active_profile())
            self.assertEqual(common.project_prefix(), "RE")
            common.set_context(self.root, "old-seed")                  # but naming it works
            self.assertEqual(common.project_prefix(), "OS")

    def test_client_reel_profile_id_layers_the_shipped_seed(self):
        prof = self.root / "output/client_database/reel-profile"
        prof.mkdir(parents=True)
        (prof / "profile.json").write_text(json.dumps({"id": "example-clinic", "prefix": "XX"}), encoding="utf-8")
        common.set_context(self.root)
        self.assertEqual(common.active_profile(), "example-clinic")
        self.assertEqual(common.project_prefix(), "XX")                   # the client's own copy wins
        self.assertEqual(common.brand_fallback("primary"), "#2A7FBA")     # seed values still underneath

    def test_generic_and_client_override(self):
        other = Path(self.tmp.name) / "dr sherif"
        (other / "assets").mkdir(parents=True)
        (other / "data").mkdir()
        common.set_context(other)
        self.assertIsNone(common.active_profile())
        self.assertEqual(common.project_prefix(), "RE")
        self.assertIsNone(common.load_config("transcription.json")["initial_prompt"])
        r = subprocess.run([sys.executable, str(SK / "engine/reel/cli.py"), "--root", str(other), "client-init",
                            "--id", "dr-sherif", "--prefix", "SH"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        prof = other / "output/client_database/reel-profile"
        (prof / "brand.json").write_text(json.dumps({"fallback_colors": {"primary": "#AA0000"}}))
        common.set_context(other)
        self.assertEqual(common.active_profile(), "dr-sherif")
        self.assertEqual(common.project_prefix(), "SH")
        self.assertEqual(common.brand_fallback("primary"), "#AA0000")
        self.assertEqual(common.brand_fallback("ink"), "#1E2A3B")     # untouched keys fall back to defaults
        self.assertFalse(any((other / d).exists() and any((other / d).iterdir()) for d in ("assets", "data")))

    def test_merged_example_clinic_keeps_the_tuned_values(self):
        """Regression: the generic defaults + the example-clinic profile keep the tuned graphics values."""
        common.set_context(self.root, "example-clinic")
        gt = common.load_config("graphics-templates.json")
        self.assertEqual(gt["templates"]["highlight_caption"]["size"], 62)
        self.assertEqual(gt["templates"]["highlight_caption"]["y"], 1180)
        self.assertIn("statement_highlight", gt["templates"])
        self.assertEqual(gt["templates"]["hook_title"]["bar_style"], "box")          # the profile's own override
        self.assertEqual(common.content_domain(), "medical")
        self.assertIn("botox", common.load_config("medical-glossary.json")["terms"]["english"])


class TestCLIOptions(ClientFixture):
    def test_global_options_after_subcommand(self):
        for argv in (["next", "--root", str(self.root), "--video-id", "C0001", "--profile", "example-clinic"],
                     ["--root", str(self.root), "--video-id", "C0001", "--profile", "example-clinic", "next"]):
            r = subprocess.run([sys.executable, str(SK / "engine/reel/cli.py"), *argv], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["profile"], "example-clinic")

    def test_no_profile_without_naming_it(self):
        r = subprocess.run([sys.executable, str(SK / "engine/reel/cli.py"), "next", "--root", str(self.root),
                            "--video-id", "C0001"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(json.loads(r.stdout)["profile"])


class TestEditorEdits(ClientFixture):
    """The editor keeps working in the built .prproj; that must not invalidate our verification, and a rebuild
    must not silently replace their work."""
    def test_editor_saves_after_build(self):
        import time
        from lib.common import Paths
        from lib import verify, ppro_build
        common.set_context(self.root, "example-clinic")
        p = Paths(self.root, "C0001")
        prj = p.p("07_premiere/project/C0001_EC_EDIT.prproj")
        prj.parent.mkdir(parents=True)
        prj.write_text("built")
        built = time.time() - 3600
        os.utime(prj, (built, built))
        common.write_json(p.p("07_premiere/ppro-build-result.json"),
                          {"status": "PRPROJ_BUILT", "project": str(prj), "prproj_mtime": built})
        self.assertIsNone(verify.editor_modified(p))
        self.assertAlmostEqual(verify.newest_render_mtime(p), built, delta=1)
        prj.write_text("editor saved changes")                       # editor saves now
        self.assertIsNotNone(verify.editor_modified(p))
        self.assertAlmostEqual(verify.newest_render_mtime(p), built, delta=1)   # verification not made stale
        from unittest import mock
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch.object(ppro_build, "job_data", return_value={"_missing": [], "project_path": str(prj)}):
            r = ppro_build.build(p, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT")
        self.assertEqual(prj.read_text(encoding="utf-8"), "editor saved changes")       # untouched


class TestRTLLineDirection(unittest.TestCase):
    """A line that STARTS with a Latin word inside Arabic text must still read right-to-left
    (found live on C0238 GFX_003: 'evidence إنها ممكن تساعد' rendered with 'evidence' on the left)."""
    def test_latin_first_word_stays_rightmost(self):
        from lib import ct_text
        if not ct_text.AVAILABLE:
            self.skipTest("CoreText not available")
        import CoreText
        font = ct_text.CTFontSpec("Helvetica", 40)
        line = ct_text._line("evidence إنها ممكن تساعد", font, (255, 255, 255))
        runs = []
        for r in CoreText.CTLineGetGlyphRuns(line):
            rng, n = CoreText.CTRunGetStringRange(r), CoreText.CTRunGetGlyphCount(r)
            if n:
                runs.append((rng.location, rng.length, min(p.x for p in CoreText.CTRunGetPositions(r, (0, n), None))))
        # the renderer may prepend a direction mark, so locate runs by what they contain, not by index
        lead = 1 if runs and min(r[0] for r in runs) == 0 and len(runs) > 6 else 0
        latin = next(x for loc, ln, x in runs if loc <= lead < loc + ln)                  # run holding "e" of evidence
        arabic = [x for loc, ln, x in runs if loc >= lead + 9 and ln >= 4]               # the Arabic words
        self.assertTrue(all(latin > x for x in arabic), f"first (Latin) word must be RIGHTMOST: {runs}")


class TestJumpCutZoom(unittest.TestCase):
    """Every cut after a removed pause must change the zoom, also inside a punch-in that spans the cut
    (found by QC on C0238: frames 61, 623, 1005 kept 1.06/1.1/1.08 on both sides)."""
    def test_every_cut_changes_scale(self):
        from lib.timemap import TimeMap
        keep = [(0, 2000), (2400, 4000), (4500, 6000), (6300, 6400), (6800, 9000)]
        cam = [{"at_ms": 1000, "until_ms": 5000, "scale_factor": 1.1, "type": "punch_in", "decision_id": "E1"}]
        ps = TimeMap(keep, cam).pieces
        for a, b in zip(ps, ps[1:]):
            if b["keep_index"] != a["keep_index"]:
                self.assertNotAlmostEqual(a["scale_factor"], b["scale_factor"], msg=f"unmasked cut at {b['start_frame']}")
        self.assertTrue(all(p["scale_factor"] <= 1.2 + 1e-9 for p in ps))

    def test_max_scale_steps_back_out(self):
        from lib.timemap import TimeMap
        cam = [{"at_ms": 0, "until_ms": 9000, "scale_factor": 1.18, "type": "punch_in", "decision_id": "E1"}]
        ps = TimeMap([(0, 2000), (2500, 4000)], cam).pieces
        self.assertAlmostEqual(ps[1]["scale_factor"], 1.12)


class TestGraphicStyle(unittest.TestCase):
    def _bar_bbox(self, style):
        from lib import previews
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            t = {"size": 86, "y": 1080, "bar_style": style}
            b = previews.Brand(Path(d))
            out = Path(d) / "bar.png"
            previews.render_event({"template": "hook_title", "params": {"text": "ممكن من أول أسبوع"}}, t, b, {}, None,
                                  out, layer="bars")
            return Image.open(out).getchannel("A").getbbox()

    def test_hook_box_covers_text_height(self):
        under, box = self._bar_bbox("underline"), self._bar_bbox("box")
        self.assertGreater(box[3] - box[1], 1.8 * (under[3] - under[1]), (under, box))

    def test_photo_crop_prefers_explicit_centre(self):
        from lib import previews
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "p.png"
            im = Image.new("RGB", (400, 1000), "white")
            im.paste((255, 0, 0), (0, 0, 400, 100))          # red band at the very top
            im.save(src)
            top = previews._fit_image(str(src), 400, 300, 0, centering=(0.5, 0.0))
            self.assertEqual(top.getpixel((200, 10))[:3], (255, 0, 0))


class TestBridgeSync(unittest.TestCase):
    def test_sync_copies_into_stable_folder(self):
        with tempfile.TemporaryDirectory() as h:
            env = {k: v for k, v in os.environ.items() if k not in ("WHYNOT_HOME", "REEL_HOME")}
            env["WHYNOT_HOME"] = h
            code = ("import sys; sys.path.insert(0, %r); from lib import ppro_bridge as b; "
                    "r1 = b.sync_scripts(); r2 = b.sync_scripts(); "
                    "print(r1['synced'], r2['synced'], b.LIB.exists(), str(b.LIB).startswith(%r))") % (str(SK / "engine/reel"), h)
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
            self.assertEqual(r.stdout.split(), ["True", "False", "True", "True"], r.stderr)

    def test_bridge_js_whitelists_stable_folder(self):
        js = (SK / "templates/premiere/cep_bridge/js/bridge.js").read_text(encoding="utf-8")
        self.assertIn("'ppro-scripts'", js)
        self.assertNotIn(".claude", js)


class TestPluginLayout(unittest.TestCase):
    def test_manifest_and_components(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(pj["name"], "whynot-cut")
        for d in ("skills", "agents", "hooks"):
            self.assertTrue((SK / d).is_dir(), d)
        for f in (SK / "agents").glob("*.md"):
            head = f.read_text(encoding="utf-8").split("---")[1]
            self.assertIn(f"name: {f.stem}", head, f)
            self.assertIn("description:", head, f)
        for f in (SK / "skills").glob("*/SKILL.md"):
            head = f.read_text(encoding="utf-8").split("---")[1]
            self.assertIn("description:", head, f)
            self.assertLess(len(f.read_text(encoding="utf-8").splitlines()), 400, f)

    def test_no_appledouble_or_hardcoded_skill_paths(self):
        bad = [p for p in SK.rglob("._*")]
        self.assertEqual(bad, [])
        for p in list((SK / "engine").rglob("*.py")) + list((SK / "templates").rglob("*.js")):
            self.assertNotIn(".claude/skills", p.read_text(encoding="utf-8"), p)


class TestShippedProfiles(unittest.TestCase):
    """No real client ships in the product: only the blank `_template` and fictional `example-*` profiles."""
    def test_only_template_and_examples_ship(self):
        names = sorted(d.name for d in (SK / "profiles").iterdir() if d.is_dir())
        self.assertIn("_template", names)
        self.assertIn("example-clinic", names)
        self.assertEqual([n for n in names if n != "_template" and not n.startswith("example-")], [])

    def test_example_clinic_has_every_file_kind(self):
        ex = SK / "profiles/example-clinic"
        kinds = {"brand.json", "medical-glossary.json", "notes.md", "profile.json", "style.json", "transcription.json",
                 "graphics-templates.json"}
        have = {f.name for f in ex.iterdir()}
        self.assertTrue(kinds <= have, kinds - have)
        for f in (SK / "profiles/_template").iterdir():
            self.assertIn(f.name, have, f"example-clinic lacks {f.name} that _template has")
        for f in ex.glob("*.json"):
            json.loads(f.read_text(encoding="utf-8"))                      # valid JSON
        prof = json.loads((ex / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(prof["id"], "example-clinic")
        self.assertEqual(prof["domain"], "medical")
        self.assertEqual(prof["prefix"], "EC")
        text = "".join(f.read_text(encoding="utf-8") for f in ex.iterdir())
        self.assertIn("Example Clinic", text)
        self.assertIn("عيادة مثال", text)
        self.assertIn("Dr. Sample Example", text)

    def test_no_real_client_name_in_the_product(self):
        """Only the legacy engine-home folder name of the original skill (read for upgrades, dropped in 4.0) may remain."""
        legacy_home = ".dr-nahla-editor"
        hits = [str(p.relative_to(SK)) for p in SK.rglob("*")
                if p.is_file() and p.suffix in (".md", ".py", ".json", ".js", ".sh", ".txt", "")
                and p.name != "CHANGELOG.md" and p.relative_to(SK).parts[0] != "tests"
                and "nahla" in p.read_text(encoding="utf-8", errors="ignore").replace(legacy_home, "").lower()]
        self.assertEqual(hits, [])


def _load_package_module():
    pk = SK.parent / "package.py"                                           # not shipped inside the plugin zip
    if not pk.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("whynot_package", pk)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPackageProfileRule(unittest.TestCase):
    """package.py refuses to build a zip that contains any profile except `_template` and `example-*`."""
    def setUp(self):
        self.pk = _load_package_module()
        if self.pk is None:
            self.skipTest("package.py is not part of this layout")
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowed_profiles_pass(self):
        for n in ("_template", "example-clinic", "example-salon"):
            (self.dir / n).mkdir()
        (self.dir / "README.md").write_text("a file, not a profile")
        self.assertEqual(self.pk.disallowed_profiles(self.dir), [])

    def test_any_other_profile_is_refused(self):
        for n in ("_template", "example-clinic", "dr-someone", "examples", "Example-x", "_private"):
            (self.dir / n).mkdir()
        self.assertEqual(self.pk.disallowed_profiles(self.dir), ["Example-x", "_private", "dr-someone", "examples"])

    def test_missing_profiles_folder_is_fine(self):
        self.assertEqual(self.pk.disallowed_profiles(self.dir / "nope"), [])

    def test_the_shipped_profiles_folder_passes(self):
        self.assertEqual(self.pk.disallowed_profiles(SK / "profiles"), [])

    def test_main_exits_1_with_a_message_and_builds_no_zip(self):
        import contextlib
        import io
        from unittest import mock
        (self.dir / "dr-someone").mkdir()
        err = io.StringIO()
        with mock.patch.object(self.pk, "PROFILES_DIR", self.dir), mock.patch.object(self.pk.zipfile, "ZipFile") as zf,                 contextlib.redirect_stderr(err):
            code = self.pk.main()
        self.assertEqual(code, 1)
        self.assertIn("dr-someone", err.getvalue())
        self.assertIn("how:", err.getvalue())
        zf.assert_not_called()


def _git_index_modes(root: Path) -> dict[str, str]:
    """Repo-relative path -> git index mode for every tracked file. Skips when git or a git checkout is missing."""
    import shutil
    if shutil.which("git") is None:
        raise unittest.SkipTest("git is not installed")
    if not (root / ".git").exists():
        raise unittest.SkipTest("not a git checkout (e.g. running from an unzipped release)")
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-s"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise unittest.SkipTest(f"git ls-files failed: {r.stderr.strip()}")
    modes = {}
    for line in r.stdout.splitlines():
        meta, _, path = line.partition("\t")
        modes[path] = meta.split()[0]
    return modes


def _expected_exec_paths() -> set[str]:
    """Repo-relative paths that must be 100755 in git: the plugin's executables, every hooks/*.py, and tools/test.sh."""
    plugin = {"whynot-cut/bin/reel", "whynot-cut/hooks/run_python.sh", "whynot-cut/setup/setup_env.sh",
              "whynot-cut/setup/setup_env.py", "whynot-cut/examples/make_demo.py"}
    hooks = {f"whynot-cut/hooks/{p.name}" for p in (SK / "hooks").glob("*.py")}
    return plugin | hooks | {"tools/test.sh"}


class TestExecutableBits(unittest.TestCase):
    """core.filemode is off on Windows, so the exec bit must be set in git's index; package.py's zip modes must match it."""
    def setUp(self):
        self.modes = _git_index_modes(SK.parent)

    def test_index_mode_is_100755_for_exactly_the_executables(self):
        want = _expected_exec_paths()
        got = {p for p, m in self.modes.items() if m == "100755"}
        self.assertEqual(sorted(got), sorted(want))
        for p in sorted(want):
            self.assertEqual(self.modes.get(p), "100755", p)

    def test_zip_exec_set_matches_git_index(self):
        pk = _load_package_module()
        if pk is None:
            self.skipTest("package.py is not part of this layout")
        git_plugin = {p[len("whynot-cut/"):] for p, m in self.modes.items()
                      if m == "100755" and p.startswith("whynot-cut/")}
        self.assertEqual(sorted(pk.EXEC), sorted(git_plugin))


if __name__ == "__main__":
    unittest.main()
