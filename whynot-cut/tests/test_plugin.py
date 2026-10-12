"""Plugin-level tests: hooks (guardrails), client profiles, bridge script sync, CLI gates.
Run:  ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
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
                   "find data -name '*.MP4' -delete", "find assets -exec rm {} +", "find . -name '*.MP4' -delete",
                   "find output -fprint data/Raw/list.txt"]
        for c in blocked:
            self.assertEqual(self.bash(c), 2, c)
        ok = ["cp -t output/projects/C0001 data/Raw/C0001.MP4", "find data -name '*.MP4'",
              "find . -name '*.tmp' -delete",                     # T11: narrowed away from the sources, as with xargs
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

    def test_g70_doctor_fix_marks_only_the_given_client(self):
        """G70 (live smoke): `doctor --fix` wrote the marker into EVERY client under clients_root. It marks only --root
        (or the cwd client); `--fix --all-clients` lists the unmarked clients and writes only with `--yes`."""
        croot = self.base / "clients"
        a, b, c = (self.site(n, croot) for n in ("Dr A", "Dr B", "Dr C"))
        env = isolated_env({"WHYNOT_CLIENTS_ROOT": str(croot), "CLAUDE_CONFIG_DIR": str(self.base / "cfg")})

        def doctor(*args, cwd=None):
            r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), *args], capture_output=True,
                               text=True, encoding="utf-8", env=env, cwd=str(cwd or self.base))
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        rep = doctor("doctor")                                           # report only: hint, nothing written
        self.assertFalse(any((x / MARKER).exists() for x in (a, b, c)))
        hints = [f["fix"] for f in rep["fixes"] if "without the .whynot-client marker" in f["item"]]
        self.assertEqual(hints, ["reel doctor --fix --all-clients"])
        rep = doctor("--root", str(a), "doctor", "--fix")
        self.assertTrue((a / MARKER).is_file())
        self.assertFalse((b / MARKER).exists() or (c / MARKER).exists())
        self.assertEqual([Path(p) for p in rep["client_markers"]["written"]], [a.resolve() / MARKER])
        doctor("doctor", "--fix", cwd=b)                                 # the cwd client (it has output/)
        self.assertFalse((b / MARKER).exists())                          # no output/ yet: not a known client folder
        (b / "output").mkdir()
        doctor("doctor", "--fix", cwd=b)
        self.assertTrue((b / MARKER).is_file())
        self.assertFalse((c / MARKER).exists())
        rep = doctor("doctor", "--fix", "--all-clients")                 # lists, writes nothing
        self.assertFalse((c / MARKER).exists())
        self.assertEqual([Path(p) for p in rep["client_markers"]["missing"]], [c.resolve()])
        self.assertIn("--all-clients --yes", rep["how"])
        rep = doctor("doctor", "--fix", "--all-clients", "--yes")
        self.assertTrue((c / MARKER).is_file())
        self.assertEqual([Path(p) for p in rep["client_markers"]["written"]], [c.resolve() / MARKER])

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
        """The guard's own heartbeat (guard-ok) counts, not the runner's hooks-ok (gate G1: always fresh here)."""
        import time
        data = Path(self.tmp.name) / "pdata"
        data.mkdir()
        old = time.time() - 3 * 86400
        start = data / "last-session-start"
        self.assertNotIn("protection may be OFF", self.ctx(data))        # no earlier session: a new install
        self.assertTrue(start.is_file())
        (data / "hooks-ok").write_text("1", encoding="utf-8")            # the runner ran, the guard never did
        self.assertIn("protection may be OFF", self.ctx(data))           # missing after a session
        hb = data / "guard-ok"
        hb.write_text("1", encoding="utf-8")
        self.assertNotIn("protection may be OFF", self.ctx(data))        # the guard ran in the last session
        os.utime(hb, (old, old))
        start.write_text(str(old - 3600), encoding="utf-8")              # a weekend off: no session since
        self.assertNotIn("protection may be OFF", self.ctx(data))        # (N4: no false alarm after idle days)
        self.assertIn("protection may be OFF", self.ctx(data))           # a session ran since, the guard did not

    def test_heartbeat_warning_through_the_hook_runner(self):
        """G1 end to end: run_python.sh touches hooks-ok right before session_context runs; the warning still fires."""
        import time
        bash = find_bash()
        engine = _isolation.REAL_ENGINE_HOME          # read only: its interpreter runs the hooks (G79 sandbox)
        if not bash or not (engine / "venv").is_dir():
            self.skipTest("needs bash and the engine venv")
        data = Path(self.tmp.name) / "pdata2"
        data.mkdir()
        (data / "last-session-start").write_text(str(time.time() - 86400), encoding="utf-8")

        def ctx():
            env = isolated_env({"CLAUDE_PLUGIN_DATA": str(data), "CLAUDE_PLUGIN_ROOT": str(SK),
                                "WHYNOT_HOME": str(engine)})
            r = subprocess.run([bash, str(SK / "hooks/run_python.sh"), str(SK / "hooks/session_context.py")],
                               input=json.dumps({"cwd": str(self.root)}), capture_output=True, text=True,
                               encoding="utf-8", env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("protection may be OFF", ctx())
        self.assertTrue((data / "hooks-ok").is_file())
        subprocess.run([bash, str(SK / "hooks/run_python.sh"), str(SK / "hooks/guard.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(self.root)}),
                       capture_output=True, text=True, encoding="utf-8",
                       env=isolated_env({"CLAUDE_PLUGIN_DATA": str(data), "CLAUDE_PLUGIN_ROOT": str(SK),
                                         "WHYNOT_HOME": str(engine)}))
        self.assertTrue((data / "guard-ok").is_file())
        self.assertNotIn("protection may be OFF", ctx())

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
            runner = cfg / "plugins/data/whynot-cut-thewhynot-ai/hooks-ok"     # the runner alone is not the guard
            runner.parent.mkdir(parents=True)
            runner.write_text("1", encoding="utf-8")
            st = onboard.guard_heartbeat()
            self.assertFalse(st["active"])
            self.assertEqual(Path(st["runner_file"]), runner)
            hb = cfg / "plugins/data/whynot-cut-thewhynot-ai/guard-ok"
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


class TestGuardReviewRound1(ClientFixture):
    """T1.5 review fix round 1: wrapper shells, script blocks, the client folder itself, globs and $PWD, prefixes,
    heredoc/here-string shells, loop variables, marker protection, xargs forms, case, roles through wrappers."""

    def run_tool(self, tool, cmd, agent=None, cwd=None, env=None):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd or self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p, env)[0]

    def blocked(self, tool, cmds, cwd=None, agent=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, agent, cwd), 2, c)

    def allowed(self, tool, cmds, cwd=None, agent=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, agent, cwd), 0, c)

    def test_i1_cmd_double_slash(self):
        self.blocked("Bash", ['cmd //c "del data\\Raw\\C0001.MP4"', 'cmd //c "rd /s /q data"',
                              "cmd //c reg add 'HKCU\\Software\\Adobe\\CSXS.11' //v PlayerDebugMode //d 1 //f",
                              'cmd //k "del data\\Raw\\C0001.MP4"', 'cmd /r del data/Raw/C0001.MP4'])
        self.allowed("Bash", ['cmd //c "dir data"', "cmd //c reg query 'HKCU\\Software\\Adobe\\CSXS.11'"])

    def test_i2_cmd_separators(self):
        self.blocked("PowerShell", ['cmd /c "echo hi & del data\\Raw\\C0001.MP4"', 'cmd /c "cd data & del /q /s *"',
                                    'cmd /c "dir && rd /s /q data"', 'cmd /c "dir || del data\\Raw\\C0001.MP4"',
                                    'cmd /c "dir | del data\\Raw\\C0001.MP4"'])
        self.blocked("Bash", ['cmd /c "cd data && del /q Raw\\*"'])
        self.allowed("PowerShell", ['cmd /c "echo hi & dir data"', 'cmd /c "echo a ^& del data\\Raw\\C0001.MP4"'])

    def test_i3_powershell_script_blocks(self):
        self.blocked("Bash", ['''powershell -NoProfile -Command "& {Remove-Item -LiteralPath 'data\\Raw\\C0001.MP4'}"''',
                              '''powershell -Command "& {Set-ItemProperty -Path 'HKCU:\\Software\\Adobe\\CSXS.11' -Name PlayerDebugMode -Value 1}"'''])
        self.blocked("PowerShell", ["& { Remove-Item data/Raw/C0001.MP4 }", "try { Remove-Item data\\Raw\\C0001.MP4 } catch {}",
                                    "foreach ($f in Get-ChildItem data/Raw) { Remove-Item $f.FullName }",
                                    "if (Test-Path output) { Remove-Item -Recurse data }",
                                    "Get-ChildItem data/Raw | ForEach-Object { [IO.File]::Delete($_.FullName) }"])
        self.allowed("PowerShell", ["Get-ChildItem data/Raw | ForEach-Object { Add-Content output/log.txt $_.Name }",
                                    'gci data/Raw | % { ffmpeg -i $_.FullName -y "output/$($_.BaseName).wav" }',
                                    "gci data/Raw | % { Copy-Item $_.FullName output/ }",
                                    "& { Get-ChildItem data/Raw }", "foreach ($f in Get-ChildItem output) { Remove-Item $f.FullName }"])

    def test_i4_client_folder_globs_and_pwd(self):
        parent = self.root.parent
        self.blocked("Bash", ["rm -rf *", "rm -rf .", "rm -rf da*", "rm -rf d?ta", 'rm "$PWD/data/Raw/C0001.MP4"',
                              'rm -rf "$(pwd)/data"', 'rm -rf "${PWD}/assets"', 'cd "$PWD/data" && rm -rf *',
                              "mv . /tmp/elsewhere"])
        self.blocked("PowerShell", ["Remove-Item * -Recurse -Force", 'Remove-Item "$PWD\\data\\Raw\\C0001.MP4"',
                                    '[IO.File]::Delete("$PWD\\data\\Raw\\C0001.MP4")', "Remove-Item -Recurse -Force ."])
        self.blocked("Bash", [f'rm -rf "{self.root.name}"', f'mv "{self.root.name}" /tmp/x', "rm -rf ."], cwd=parent)
        self.blocked("PowerShell", [f'Remove-Item -Recurse -Force "{self.root.name}"'], cwd=parent)
        self.allowed("Bash", ["rm -rf output/projects/C0001/tmp", "rm -f output/*.tmp", "mv output/a.mp4 .",
                              'rm "$PWD/output/x.json"', "rm -rf o*/projects/C0001/cache"])
        self.allowed("PowerShell", ["Remove-Item output/*.tmp", "Remove-Item -Recurse output/projects/C0001/cache"])

    def test_i5_prefixes_eval_heredoc_loops(self):
        self.blocked("Bash", ["timeout 60 rm data/Raw/C0001.MP4", "nice rm -rf data", "nice -n 5 rm -rf data",
                              "nohup rm data/Raw/C0001.MP4", "env -i rm data/Raw/C0001.MP4", "time rm data/Raw/C0001.MP4",
                              "eval rm data/Raw/C0001.MP4", "eval 'rm -rf data'",
                              "bash <<'EOF'\nrm -rf data\nEOF", "cat <<EOF | sh\nrm data/Raw/C0001.MP4\nEOF",
                              'bash <<< "rm -rf data"', "for f in data/Raw/*.MP4; do rm \"$f\"; done",
                              "f=data/Raw/C0001.MP4; rm \"$f\""])
        self.blocked("PowerShell", ['Invoke-Expression "Remove-Item data/Raw/C0001.MP4"', "iex 'Remove-Item -Recurse data'",
                                    "$f = Get-ChildItem data/Raw; $f | Remove-Item", "(Get-Item data\\Raw\\C0001.MP4).Delete()",
                                    "$x = Get-Item data/Raw/C0001.MP4; $x.MoveTo('output/a.mp4')"])
        self.allowed("Bash", ["python - <<'EOF'\nimport os; os.remove('data/Raw/C0001.MP4')\nEOF",
                              "cat <<EOF > output/notes.md\nrm -rf data\nEOF", "for f in data/Raw/*.MP4; do echo \"$f\"; done",
                              "for f in output/*.tmp; do rm \"$f\"; done", "timeout 60 ls data/Raw"])
        self.allowed("PowerShell", ["$f = Get-ChildItem output; $f | Remove-Item", "(Get-Item output\\a.mp4).Delete()"])

    def test_m1_guard_writes_its_own_heartbeat(self):
        data = Path(self.tmp.name) / "pdata"
        data.mkdir()
        code = self.run_tool("Bash", "ls", env={"CLAUDE_PLUGIN_DATA": str(data)})
        self.assertEqual(code, 0)
        self.assertTrue((data / "guard-ok").is_file())

    def test_m2_marker_is_protected(self):
        self.blocked("Bash", ["rm .whynot-client", "echo {} > .whynot-client", "mv .whynot-client output/"])
        self.blocked("PowerShell", ["Remove-Item .whynot-client"])
        code = hook(GUARD, {"tool_name": "Write", "cwd": "/",
                            "tool_input": {"file_path": str(self.root / ".whynot-client"), "content": "x"}})[0]
        self.assertEqual(code, 2)
        self.allowed("Bash", ["cat .whynot-client"])

    def test_m3_xargs_forms(self):
        self.blocked("Bash", ["ls data/Raw/*.MP4 | xargs rm.exe", "ls data/Raw/*.MP4 | xargs.exe rm",
                              "ls data/Raw/*.MP4 | xargs sh -c 'rm \"$@\"' _", "ls data/Raw/*.MP4 | xargs -I{} cp /dev/null {}",
                              "ls data/Raw/*.MP4 | xargs -I % mv % output/"])
        self.allowed("Bash", ["ls data/Raw | xargs -I{} rm output/{}.wav", "ls data/Raw | xargs -I{} cp data/Raw/{} output/",
                              "ls data/Raw/*.MP4 | xargs sh -c 'ffprobe \"$@\"' _"])

    def test_m4_case_insensitive(self):
        self.blocked("Bash", ["RM data/Raw/C0001.MP4", "Rm -RF DATA", "mkdir -p DATA/new/deep", "touch Assets/x.txt"])
        self.blocked("PowerShell", ["REMOVE-ITEM -Recurse -Force DATA"])
        code = hook(GUARD, {"tool_name": "Write", "cwd": str(self.root),
                            "tool_input": {"file_path": "DATA/new/deep/x.txt", "content": "x"}})[0]
        self.assertEqual(code, 2)

    def test_m6_roles_through_wrappers(self):
        te, qc = "whynot-cut:transcript-editor", "whynot-cut:qc-reviewer"
        self.blocked("Bash", ["timeout 600 reel transcript-verify --by editor",
                              'bash "$CLAUDE_PLUGIN_ROOT/bin/reel" transcript-verify --by editor',
                              'sh /x/whynot-cut/bin/reel transcript-verify --by=editor',
                              "nohup reel transcript-verify --by editor"], agent=te)
        self.blocked("Bash", ["py -3 engine/reel/cli.py ref-analyze", "timeout 60 reel ppro-build"], agent=qc)
        self.blocked("PowerShell", ["& reel transcript-verify --by \"editor\""], agent=te)
        self.allowed("Bash", ["timeout 600 reel transcript-verify --by editor"])

    def test_m7_session_context_nudges_unmarked_client(self):
        legacy = Path(self.tmp.name) / "Old Client"
        for d in ("assets", "data/Raw", "output/projects"):
            (legacy / d).mkdir(parents=True)
        code, out, _ = hook(CTX, {"cwd": str(legacy)})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("without a marker", ctx)
        self.assertIn("reel doctor --fix", ctx)
        hugo = Path(self.tmp.name) / "HugoSite"
        for d in ("assets", "data"):
            (hugo / d).mkdir(parents=True)
        self.assertEqual(hook(CTX, {"cwd": str(hugo)})[1].strip(), "")      # no output/: not a WhyNot Cut folder

    def test_review_false_positives_stay_allowed(self):
        self.allowed("Bash", ["git rm -r --cached data", "git stash list", "ffmpeg -i data/Raw/C0001.MP4 -c copy output/x.mp4",
                              "ls data/Raw | tee output/list.txt", "find output -name '*.tmp' -delete",
                              "echo '$(rm data/Raw/C0001.MP4)'"])
        self.blocked("Bash", ["git stash --include-untracked", "git stash"])
        self.blocked("PowerShell", ["cd HKCU:\\Software\\Adobe; Set-ItemProperty CSXS.11 PlayerDebugMode 1"])
        self.allowed("PowerShell", ["Get-Content data/Raw/x.srt | Set-Content output/list.txt",
                                    "Get-ChildItem data/Raw | Select-Object Name | Out-File output/list.txt"])


class TestGuardReviewRound2(ClientFixture):
    """T1.5 review round 2: .NET sub-expressions (regression), loop variables inside output/ paths (false positives),
    and the generalisation gaps the re-review found."""

    def run_tool(self, tool, cmd, agent=None, cwd=None):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd or self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def blocked(self, tool, cmds, cwd=None, agent=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, agent, cwd), 2, c)

    def allowed(self, tool, cmds, cwd=None, agent=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, agent, cwd), 0, c)

    def test_n1_dotnet_sub_expressions(self):
        self.blocked("PowerShell", [
            "[IO.File]::Delete((Join-Path $PWD 'data/Raw/C0001.MP4'))",
            "[IO.File]::Delete((Resolve-Path 'data/Raw/C0001.MP4'))",
            "[IO.File]::Delete([IO.Path]::Combine('data','Raw','C0001.MP4'))",
            '[IO.Directory]::Delete((Resolve-Path "data"), $true)',
            '[IO.File]::WriteAllText((Join-Path (Get-Location) "data\\Raw\\C0001.MP4"), "")',
            '[IO.File]::Copy("output/x", (Join-Path $PWD "data/Raw/C0001.MP4"), $true)',
            '[IO.File]::Delete("data/Raw/" + "C0001.MP4")', "[IO.File]::Delete( 'data/Raw/C0001.MP4' )"])
        self.blocked("Bash", ['''powershell -c "[IO.File]::Delete((Join-Path $PWD 'data/Raw/C0001.MP4'))"'''])
        self.allowed("PowerShell", [
            '[IO.File]::Copy((Join-Path $PWD "data/Raw/C0001.MP4"), "output/a.mp4", $true)',
            '[IO.File]::WriteAllText("output/list.txt", (Get-ChildItem data/Raw | Out-String))'])

    def test_n2_loop_variables_inside_output_paths(self):
        self.allowed("Bash", [
            'for f in data/Raw/*.MP4; do ffmpeg -i "$f" "output/$(basename "$f" .MP4).wav"; done',
            'for f in data/Raw/*.MP4; do ffmpeg -i "$f" "output/${f##*/}.wav"; done',
            'for f in data/Raw/*.MP4; do cp "$f" "output/$(basename "$f")"; done',
            'for f in data/Raw/*.MP4; do rm -f "output/$(basename "$f").wav"; done',
            'f=data/Raw/C0001.MP4; ffmpeg -i "$f" -y "output/${f##*/}.wav"'])
        self.blocked("Bash", ['for f in data/Raw/*; do rm "$f"; done', 'F=data && rm -rf "${F%/}"',
                              'for f in data/Raw/*; do mv "$f" "$f.bak"; done', 'f="$PWD/data"; rm -rf "$f"'])

    def test_cmd_gaps(self):
        self.blocked("PowerShell", ['cmd /c "if exist data del /q data\\Raw\\*"',
                                    'cmd /c "if not exist output\\x del /q data\\Raw\\C0001.MP4"',
                                    'cmd /c "for %f in (data\\Raw\\*) do del %f"',
                                    'cmd /c del %CD%\\data\\Raw\\C0001.MP4'])
        self.blocked("Bash", ["cmd /cdel data\\\\Raw\\\\C0001.MP4", 'cmd //cdel "data\\Raw\\C0001.MP4"'])
        self.allowed("PowerShell", ['cmd /c "if exist data dir data"', 'cmd /c "for %f in (data\\Raw\\*) do echo %f"',
                                    'cmd /c "for %f in (output\\*.tmp) do del %f"'])

    def test_powershell_gaps(self):
        self.blocked("PowerShell", ["foreach($f in gci data/Raw){ri $f}",
                                    'Invoke-Expression -Command "Remove-Item data/Raw/C0001.MP4"',
                                    '"Remove-Item data/Raw/C0001.MP4" | iex',
                                    "'Remove-Item -Recurse data' | powershell -Command -",
                                    '[IO.FileInfo]::new("data/Raw/C0001.MP4").Delete()',
                                    "Get-ChildItem | Remove-Item -Recurse -Force", "gci . | ri -r -fo",
                                    '$env:X = "data"; Remove-Item -Recurse $env:X', '$d = "da" + "ta"; Remove-Item -Recurse $d',
                                    "$s = @'\nRemove-Item -Recurse data\n'@; iex $s"])
        self.allowed("PowerShell", ["Get-ChildItem output | Remove-Item -Recurse -Force", "gci | Select-Object Name",
                                    '"Get-ChildItem data" | iex'])

    def test_bash_gaps(self):
        self.blocked("Bash", ["rm -rf {assets,data}", "rm -rf dat{a,}", "cd -- data && rm -rf *", "ls | xargs rm -rf",
                              'echo "rm -rf data" | bash', "printf 'rm data/Raw/C0001.MP4' | sh",
                              "export D=data; rm -rf $D", 'declare D=data; rm -rf "$D"', "readonly D=data; rm -rf $D",
                              'a=(data assets); rm -rf "${a[@]}"', "winpty rm data/Raw/C0001.MP4",
                              "watch -n1 rm -rf data", "flock /tmp/l rm data/Raw/C0001.MP4",
                              "parallel rm ::: data/Raw/*"])
        self.blocked("Bash", ["bash -e /x/bin/reel transcript-verify --by editor"], agent="whynot-cut:transcript-editor")
        self.allowed("Bash", ["rm -rf {output/a,output/b}", "ls output | xargs rm -rf", 'echo "ls data" | bash',
                              "export D=output; rm -rf $D/tmp", "cd -- output && rm -rf tmp", "ls | xargs echo"])

    def test_client_database_of_an_unmarked_client(self):
        legacy = Path(self.tmp.name) / "Legacy"
        for d in ("assets", "data/Raw", "output/client_database"):
            (legacy / d).mkdir(parents=True)
        self.blocked("Bash", ["rm -rf output/client_database"], cwd=legacy)
        self.allowed("Bash", ["rm -rf output/client_database/tmp"], cwd=legacy)

    def test_m7_nudge_only_at_a_whynot_cut_root(self):
        legacy = Path(self.tmp.name) / "Old Client"
        for d in ("assets", "data/Raw", "output/projects/C0001"):
            (legacy / d).mkdir(parents=True)
        ctx = json.loads(hook(CTX, {"cwd": str(legacy)})[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("without a marker", ctx)
        self.assertEqual(hook(CTX, {"cwd": str(legacy / "output")})[1].strip(), "")     # not in a subfolder
        repo = Path(self.tmp.name) / "ml-repo"                                          # generic data-science layout
        for d in ("assets", "data", "output"):
            (repo / d).mkdir(parents=True)
        self.assertEqual(hook(CTX, {"cwd": str(repo)})[1].strip(), "")


class TestGuardReviewRound3(ClientFixture):
    """T1.5 review round 3: words starting with $( that wrap a source variable, filtered listings feeding a recursive
    delete, filter values that are not paths, joined .NET paths with an unknown base, rsync --remove-source-files,
    Bash "$f.wav", cmd `for /r ROOT`."""

    def run_tool(self, tool, cmd, cwd=None):
        return hook(GUARD, {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd or self.root)})[0]

    def blocked(self, tool, cmds, cwd=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, cwd), 2, c)

    def allowed(self, tool, cmds, cwd=None):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c, cwd), 0, c)

    def test_subexpression_words_stay_tainted(self):
        self.blocked("PowerShell", [
            'Get-ChildItem data/Raw | ForEach-Object { Remove-Item "$($_.FullName)" }',
            'Get-ChildItem data/Raw | ForEach-Object { Remove-Item -Path "$($_.FullName)" }',
            'foreach ($f in Get-ChildItem data/Raw) { Remove-Item "$($f.FullName)" }',
            'foreach ($f in Get-ChildItem data/Raw) { Move-Item "$($f.FullName)" output/ }',
            'Get-ChildItem data/Raw | ForEach-Object { Rename-Item "$($_.FullName)" "$($_.BaseName)_old.mp4" }',
            'Get-ChildItem data/Raw *.MP4 | ForEach-Object { ffmpeg -y -i $_.FullName "$($_.DirectoryName)/$($_.BaseName).wav" }',
            'Get-ChildItem data/Raw | ForEach-Object { ffmpeg -y -i $_.FullName -c copy "$($_.FullName).fixed.mp4" }'])
        self.blocked("Bash", [
            'for f in data/Raw/*.MP4; do ffmpeg -y -i "$f" "$(dirname "$f")/$(basename "$f" .MP4).wav"; done',
            'for f in data/Raw/*; do rm "./$f"; done', 'for f in data/Raw/*.MP4; do ffmpeg -y -i "$f" "$f.wav"; done',
            'for f in data/Raw/*.MP4; do ffmpeg -y -i "$f" "${f%.MP4}.wav"; done'])
        self.allowed("PowerShell", [
            'Get-ChildItem data/Raw | ForEach-Object { ffmpeg -i "$($_.FullName)" "output/$($_.BaseName).wav" }',
            'Get-ChildItem data/Raw | ForEach-Object { Copy-Item "$($_.FullName)" "output/$($_.Name)" }'])
        self.allowed("Bash", [
            'for f in data/Raw/*.MP4; do ffmpeg -i "$f" "output/$(basename "$f").wav"; done',
            'for f in data/Raw/*.MP4; do b=${f##*/}; ffmpeg -i "$f" -y "output/${b%.*}.wav"; done',
            'for f in data/Raw/*.MP4; do name=$(basename "$f" .MP4); ffmpeg -y -i "$f" "output/$name.wav"; done'])

    def test_filtered_listings_are_not_whole_folder_deletes(self):
        self.allowed("Bash", ["find . -name '*.tmp' | xargs rm -rf", "find . -type d -name '__pycache__' | xargs rm -rf",
                              "ls | grep '\\.srt$' | xargs -I{} mv {} output/"])
        self.allowed("PowerShell", ["Get-ChildItem . -Recurse -Filter *.tmp | Remove-Item -Recurse -Force",
                                    "Get-ChildItem | Where-Object Extension -eq '.srt' | Move-Item -Destination output",
                                    "Get-ChildItem -File | Rename-Item -NewName { $_.Name.ToLower() }"])
        self.blocked("Bash", ["ls | xargs rm -rf", "find data -name '*.MP4' | xargs rm"])
        self.blocked("PowerShell", ["Get-ChildItem | Remove-Item -Recurse -Force",
                                    "Get-ChildItem -Path data -Recurse | Remove-Item -Force -Recurse"])

    def test_filter_values_are_not_paths(self):
        self.allowed("PowerShell", ["Get-ChildItem output -Filter *data* | Remove-Item",
                                    "Get-ChildItem -Path output -Filter 'data*' | Remove-Item",
                                    "Get-ChildItem output -Include *data* -Recurse | Remove-Item"])
        self.allowed("Bash", ["find output -name '*data*' | xargs rm", "find output -name 'assets*' | xargs rm -f"])

    def test_joined_dotnet_paths(self):
        self.allowed("PowerShell", ["[IO.Directory]::CreateDirectory((Join-Path 'output' 'data'))",
                                    "[IO.File]::WriteAllText([IO.Path]::Combine($out, 'data', 'x.json'), $json)",
                                    "[IO.File]::WriteAllText((Join-Path $PWD 'output' 'data.json'), $json)"])
        self.blocked("PowerShell", ["[IO.File]::Delete((Join-Path $PWD 'data/Raw/C0001.MP4'))",
                                    "[IO.File]::Delete([IO.Path]::Combine('data','Raw','C0001.MP4'))",
                                    "$f = Get-Item data/Raw; [IO.File]::Delete([IO.Path]::Combine($f, 'C0001.MP4'))"])

    def test_cheap_blocks(self):
        self.blocked("Bash", ["rsync -a --remove-source-files data/Raw/ output/"])
        self.allowed("Bash", ["rsync -a data/ output/data_copy/", "rsync -a --remove-source-files output/tmp/ output/done/"])
        self.blocked("PowerShell", ['cmd /c "for /r data %f in (*.MP4) do del %f"'])
        self.allowed("PowerShell", ['cmd /c "for /r output %f in (*.tmp) do del %f"'])


class TestGuardPhase1Minors(ClientFixture):
    """3.0 T11 (deferred review findings): only name/path/regex/newer predicates, a real -Filter/-Include, grep and
    Where-Object narrow a listing; find -delete/-exec rm follows the xargs rule; unknown-base .NET deletes with a
    multi-segment source literal; rsync --remove-sent-files; filter values on any cmdlet are not paths."""
    run_tool = TestGuardReviewRound3.run_tool
    blocked = TestGuardReviewRound3.blocked
    allowed = TestGuardReviewRound3.allowed

    def test_g1_depth_type_and_star_filters_do_not_narrow(self):
        self.blocked("Bash", ["find . -mindepth 1 -maxdepth 1 | xargs rm -rf", "find . -maxdepth 1 | xargs rm -rf",
                              "find . -type d | xargs rm -rf", "find . -type f | xargs rm",
                              "find . -empty | xargs rm -rf", "ls | head -5 | xargs rm -rf"])
        self.blocked("PowerShell", ["gci -Directory | Remove-Item -Recurse -Force",
                                    "gci -Include * | Remove-Item -Recurse", "gci -Filter * | Remove-Item -Recurse",
                                    "gci -Filter '*.*' | Remove-Item -Recurse", "gci -Recurse | Remove-Item -Force",
                                    "Get-ChildItem -Exclude *.tmp | Remove-Item -Recurse"])
        self.allowed("Bash", ["find . -name '*.tmp' | xargs rm -rf", "find . -iname '*.TMP' | xargs rm",
                              "find . -path '*/tmp/*' | xargs rm -f", "find . -regex '.*\\.tmp' | xargs rm",
                              "ls | grep '\\.srt$' | xargs rm",
                              "find output -type d -empty | xargs rm -rf", "find output -maxdepth 1 | xargs rm -rf"])
        self.allowed("PowerShell", ["gci -File -Filter *.tmp | Remove-Item", "gci -Filter *.tmp | Remove-Item -Recurse",
                                    "gci -Include *.srt -Recurse | Remove-Item",
                                    "Get-ChildItem | ? { $_.Name -like '*.tmp' } | Remove-Item -Recurse",
                                    "Get-ChildItem output -Directory | Remove-Item -Recurse -Force",
                                    "gci output -r | Remove-Item"])

    def test_g2_find_delete_and_exec_follow_the_xargs_rule(self):
        self.allowed("Bash", ["find . -name '*.tmp' -delete", "find . -name '*.tmp' -exec rm {} +",
                              "find . -name '__pycache__' -exec rm -rf {} +", "find output -type f -delete"])
        self.blocked("Bash", ["find . -delete", "find . -type d -exec rm -rf {} +", "find . -maxdepth 1 -delete",
                              "find data -name '*.tmp' -delete", "find . -type f -exec rm {} \\;"])
        # a predicate that matches the client's own files does not narrow (raw footage is *.mp4)
        self.blocked("Bash", ["find . -name '*.mp4' -delete", "find . -name '*' -delete",
                              "find . -iname '*.MP4' -exec rm {} +", "find . -name '*.mp4' | xargs rm",
                              "find . -path '*/data/*' -delete", "find . -name '*.tmp' -delete -o -path './data/*' -delete"])
        self.blocked("Bash", ["find .. -name '*.mp4' -delete"], cwd=self.root / "output")
        # fix round 1 (I1): negated predicates, -prune and -o branches without a narrowing predicate, -newer alone
        self.blocked("Bash", ["find . ! -name '*.tmp' -delete", "find . -not -name '*.tmp' -delete",
                              "find . -name '*.tmp' -o -type f -delete",
                              "find . -name '*.tmp' -prune -o -type f -delete", "find . -newer x -delete",
                              "find . ! \\( -name '*.tmp' \\) -delete", "find . -newer output/x | xargs rm -f",
                              "find . ! -name '*.tmp' | xargs rm -rf", "find . -name '*.tmp' -o -type d | xargs rm -rf"])
        self.allowed("Bash", ["find . -name '*.tmp' -o -name '*.bak' -delete", "find . -type f -name '*.tmp' -delete",
                              "find . \\( -name '*.tmp' -o -name '*.log' \\) -delete",
                              "find . ! -type d -name '*.tmp' -delete"])

    def test_c1_comments_never_hide_later_lines(self):
        """Phase 1 gate C1: a `#` comment (with an apostrophe or not) swallowed every later line of a multi-line command,
        and in PowerShell an apostrophe in a comment or a here-string opened a quote that hid the rest."""
        self.blocked("Bash", ["# they're stale\nrm -rf data", "# clean up the stale previews\nrm data/Raw/C0001.MP4",
                              "ls output # it's fine\nrm data/Raw/C0001.MP4", "# Step 1\nmv data/Raw/C0001.MP4 output/",
                              "echo start # Yunus's clip\nrm data/Raw/C0001.MP4", "# \"quoted comment\nrm data/Raw/C0001.MP4",
                              "reel next\n# then\nrm -rf output/projects/C0001", "x=1 #'\n\nrm -rf data",
                              "bash -c \"# it's\nrm -rf data\""])
        self.blocked("PowerShell", ["# it's stale\nRemove-Item data/Raw/C0001.MP4",
                                    "<# don't #>\nRemove-Item data/Raw/C0001.MP4",
                                    "<# a\nmulti-line 'comment\n#>\nRemove-Item data/Raw/C0001.MP4",
                                    "Get-ChildItem output # it's\nRemove-Item data/Raw/C0001.MP4",
                                    "$x = @'\nit's\n'@\nRemove-Item data/Raw/C0001.MP4",
                                    "$n = @\"\nit's\n\"@\nRemove-Item data/Raw/C0001.MP4"])
        self.allowed("Bash", ["ls output # rm -rf data", "echo ${#x} a#b", "echo '# not a comment'; ls output",
                              "# rm -rf data\nls output", "git log --format='%h #%s' -3"])
        self.allowed("PowerShell", ["Get-ChildItem output # Remove-Item data", "Write-Host '#5'; Get-ChildItem output",
                                    "<# Remove-Item data #> Get-ChildItem output", "$x = @'\nRemove-Item data\n'@"])

    def test_c1_round2_backslash_comments_ansi_quotes_quoted_heredoc_markers(self):
        """Gate fix round 2: a comment ending in a backslash does not continue onto the next line (N1); $'...' quoting
        (N6); `<<EOF` inside quotes opens no heredoc (N6); find's `,` splits branches (N3); a -prune branch that only
        prunes needs no narrowing (N5)."""
        self.blocked("Bash", ["# backups are in C:\\temp\\\nrm -rf data", "ls output # trailing \\\nrm -rf data",
                              "echo $'it\\'s' # x\nrm -rf data", "echo \"<<EOF\"\nrm -rf data\nEOF",
                              "find . -name '*.tmp' , -delete", "find . -name '*.tmp' , -exec rm -rf {} +",
                              "find . \\( -type f -o -name '*.tmp' \\) -delete",
                              "find . -name '*.tmp' -prune -o -type f -delete", "ls \\\n -la; rm -rf data",
                              "echo a \\\n# c\nrm -rf data"])
        self.allowed("Bash", ["find . -path ./data -prune -o -name '*.tmp' -delete",
                              "find . \\( -name '*.tmp' -o -name '*.log' \\) -delete", "ls \\\n output",
                              "echo \"<<EOF\"; ls output", "cat <<'EOF'\n# rm -rf data\nEOF"])
        def sub(cmd):
            return hook(GUARD, {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root),
                                "agent_type": "whynot-cut:story-editor"})[0]
        self.assertEqual(sub("# approve, see C:\\notes\\\nreel approve-plan --root . --video-id C0001 --by delegated"), 2)

    def test_m3_round2_file_listing_never_deletes_the_marker(self):
        self.blocked("PowerShell", ["gci -File | Remove-Item", "gci -Force -File | Remove-Item",
                                    "Get-ChildItem -File | ForEach-Object { $_ } | Remove-Item"])
        self.blocked("Bash", ["ls -a | xargs rm -f", "find . -maxdepth 1 -name '.*' | xargs rm"])
        self.allowed("PowerShell", ["gci -File -Exclude .whynot-client | Remove-Item",
                                    "Get-ChildItem -File | Rename-Item -NewName { $_.Name.ToLower() }",
                                    "gci output -File | Remove-Item"])

    def test_c1_comments_never_hide_role_gates(self):
        def run(cmd, agent):
            return hook(GUARD, {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root),
                                "agent_type": agent})[0]
        self.assertEqual(run("# record the approval\nreel approve-plan --root . --video-id C0001 --by delegated",
                             "whynot-cut:story-editor"), 2)
        self.assertEqual(run("# rebuild\nreel ppro-build --root . --video-id C0001", "whynot-cut:qc-reviewer"), 2)
        self.assertEqual(run("# Gate 1\nreel ae-build --root . --video-id C0001", None), 2)

    def test_m3_listing_of_the_client_root_never_deletes_the_marker(self):
        self.blocked("Bash", ["find . -maxdepth 1 | xargs rm", "ls -A | xargs rm -f", "find . -maxdepth 1 -type f | xargs rm"])
        self.blocked("PowerShell", ["Get-ChildItem -Force | Remove-Item", "gci -Hidden | Remove-Item"])
        self.allowed("Bash", ["find output -maxdepth 1 | xargs rm -f", "ls output | xargs cat", "ls -A | xargs cat"])

    def test_i2_scan_budget_never_trusts_a_source_pattern(self):
        """Fix round 1 (I2): a client too big to scan (budget spent) trusts only temp-style patterns."""
        for i in range(30):
            (self.root / "assets/Photos" / f"p{i}.jpg").write_bytes(b"x")
        env = {"WHYNOT_GUARD_SCAN_BUDGET": "10"}

        def run(cmd):
            return hook(GUARD, {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}, env)[0]
        for c in ("find . -name '*' -delete", "find . -name '*.mp4' -delete", "find . -name '*.jpg' -exec rm {} +",
                  "find . -name '*.json' -delete"):
            self.assertEqual(run(c), 2, c)
        for c in ("find . -name '*.tmp' -delete", "find . -name '__pycache__' -exec rm -rf {} +",
                  "find . -name .DS_Store -delete", "find . -iname 'Thumbs.db' | xargs rm -f"):
            self.assertEqual(run(c), 0, c)
        self.allowed("Bash", ["find . -name '*.mp4' -delete"], cwd=self.root / "output")
        self.blocked("PowerShell", ["gci -r | Remove-Item", "Get-ChildItem -Rec | ForEach-Object { Remove-Item $_ }",
                                    "gci -Recurse -Filter *.mp4 | Remove-Item",
                                    "Get-ChildItem -Recurse -Include *.MP4 | Remove-Item -Force",
                                    "gci -File -Recurse | Remove-Item"])
        self.allowed("PowerShell", ["gci -Recurse -Filter *.tmp | Remove-Item"])

    def test_g3_unknown_base_dotnet_delete_with_a_source_literal(self):
        self.blocked("PowerShell", ["[IO.File]::Delete((Join-Path $root 'data/Raw/C0001.MP4'))",
                                    "$root = (Get-Location).Path; [IO.File]::Delete((Join-Path $root 'data/Raw/C0001.MP4'))",
                                    "[IO.File]::Move((Join-Path $root 'data\\Raw\\C0001.MP4'), 'output/x.mp4')"])
        self.allowed("PowerShell", ["[IO.File]::WriteAllText([IO.Path]::Combine($out, 'data', 'x.json'), $json)",
                                    "[IO.File]::Delete([IO.Path]::Combine($out, 'data', 'x.json'))",
                                    "[IO.File]::Delete((Join-Path $out 'tmp/x.json'))"])

    def test_g4_rsync_remove_sent_files_alias(self):
        self.blocked("Bash", ["rsync -a --remove-sent-files data/Raw/ output/"])
        self.allowed("Bash", ["rsync -a --remove-sent-files output/tmp/ output/done/"])

    def test_g5_filter_values_on_any_cmdlet(self):
        self.allowed("PowerShell", ["Remove-Item output -Filter *data* -Recurse",
                                    "Remove-Item output/* -Include *data* -Recurse",
                                    "Remove-Item output -Recurse -Exclude data*"])
        self.blocked("PowerShell", ["Remove-Item data -Filter *.tmp -Recurse",
                                    "Remove-Item -Path data/Raw -Include *.MP4 -Recurse"])


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
        # G79: the bridge is mocked both ways - this test once queued real build_project jobs into a running Premiere
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("must not reach Premiere")) as submit, \
                mock.patch.object(ppro_build, "job_data", return_value={"_missing": [], "project_path": str(prj)}):
            r = ppro_build.build(p, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT")
        submit.assert_not_called()
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

    REAL_CLIENT_TOKENS = ("nahla", "hunter", "kasr al-ainy", "قصر العيني", "sherin", "helmy", "شيرين", "حلمي")

    def real_client_tokens(self, text: str) -> list[str]:
        """The real-client words in text; only the legacy engine-home folder name of the original skill (read for
        upgrades, dropped in 4.0) may remain."""
        low = text.replace(".dr-nahla-editor", "").lower()
        return [t for t in self.REAL_CLIENT_TOKENS if t in low]

    def test_no_real_client_name_in_the_product(self):
        self.assertEqual(self.real_client_tokens("Kasr Al-Ainy / قصر العيني, Dr. Hunter, nahla, Sherin Helmy / شيرين حلمي"),
                         list(self.REAL_CLIENT_TOKENS))
        self.assertEqual(self.real_client_tokens("~/.dr-nahla-editor is a legacy home"), [])
        hits = [(str(p.relative_to(SK)), toks) for p in SK.rglob("*")
                if p.is_file() and p.suffix in (".md", ".py", ".json", ".js", ".sh", ".txt", "")
                and p.name != "CHANGELOG.md" and p.relative_to(SK).parts[0] != "tests"
                and (toks := self.real_client_tokens(p.read_text(encoding="utf-8", errors="ignore")))]
        hits += [(str(p.relative_to(SK)), toks) for p in (SK / "tests").rglob("*.py")      # gate G4: the tests
                 if p.name != "test_plugin.py"                                           # (holds the list)
                 and (toks := [t for t in self.real_client_tokens(p.read_text(encoding="utf-8"))
                              if t not in ("nahla", "hunter", "kasr al-ainy", "قصر العيني")])]
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
        with mock.patch.object(self.pk, "PROFILES_DIR", self.dir), \
                mock.patch.object(self.pk.zipfile, "ZipFile") as zf, contextlib.redirect_stderr(err):
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


def _frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter of a SKILL.md / agent .md (PyYAML when the engine venv has it, else a strict
    parser for the `key: value` / `key: "quoted"` lines these files use)."""
    text = path.read_text(encoding="utf-8")
    head = text.split("---")[1]
    try:
        import yaml
        return yaml.safe_load(head)
    except ImportError:
        out, last = {}, None
        for line in head.splitlines():
            if line.startswith("  - ") and last:
                out[last] = (out[last] if isinstance(out[last], list) else []) + [line[4:].strip()]
            elif line and line[0] not in " -#" and ":" in line:
                last, _, val = line.partition(":")
                val = val.strip()
                out[last] = json.loads(val) if val.startswith('"') else val
        return out


class TestListingBudget(unittest.TestCase):
    """Claude Code drops skill descriptions when the listing overflows its budget (1% of the context window); a skill
    without a description stops auto-triggering. Keep the plugin's share small (3.0, D11)."""
    USER_MAX = 200
    CRAFT_MAX = 90
    TOTAL_MAX = 4000
    PLUGIN_DESC_MAX = 250
    CRAFT_AGENT = {"audio-craft": "audio-engineer", "client-craft": "client-researcher",
                   "episode-craft": "episode-analyst", "medical-accuracy": "medical-reviewer",
                   "motion-craft": "motion-designer", "premiere-craft": "premiere-builder",
                   "publish-craft": "publish-writer", "qc-craft": "qc-reviewer", "story-craft": "story-editor",
                   "transcript-craft": "transcript-editor"}

    def skills(self):
        return {f.parent.name: _frontmatter(f) for f in sorted((SK / "skills").glob("*/SKILL.md"))}

    def test_total_and_per_skill_limits(self):
        total = 0
        for name, fm in self.skills().items():
            d = fm["description"]
            total += len(d)
            limit = self.CRAFT_MAX if fm.get("user-invocable") is False else self.USER_MAX
            self.assertLessEqual(len(d), limit, f"{name}: {len(d)} chars > {limit}")
        self.assertLessEqual(total, self.TOTAL_MAX, f"all skill descriptions total {total} chars")

    def test_craft_skills_are_the_one_line_reference(self):
        skills = self.skills()
        craft = sorted(n for n, fm in skills.items() if fm.get("user-invocable") is False)
        self.assertEqual(craft, sorted(self.CRAFT_AGENT))
        for name, agent in self.CRAFT_AGENT.items():
            self.assertEqual(skills[name]["description"],
                             f"Reference for the {agent} agent (preloaded). Not for direct use.")
            self.assertNotIn("disable-model-invocation", skills[name])  # preloading needs it off

    def test_craft_skill_is_preloaded_by_the_named_agent(self):
        for name, agent in self.CRAFT_AGENT.items():
            fm = _frontmatter(SK / "agents" / f"{agent}.md")
            self.assertIn(name, fm.get("skills") or [], f"{agent} does not preload {name}")

    def test_user_skills_lead_with_the_use_and_have_arabic_triggers(self):
        for name, fm in self.skills().items():
            if fm.get("user-invocable") is False:
                continue
            d = fm["description"]
            self.assertFalse(d.startswith("This skill should be used"), f"{name}: wasted words at the start")
            self.assertRegex(d, "[\u0600-\u06ff]", f"{name}: no Arabic trigger phrase")

    def test_agent_descriptions_do_not_point_at_the_body(self):
        for f in sorted((SK / "agents").glob("*.md")):
            d = _frontmatter(f)["description"]
            self.assertNotIn("When to invoke", d, f.name)
            self.assertTrue(d.startswith("Use this agent when"), f.name)

    def test_plugin_description_fits(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(pj["description"]), self.PLUGIN_DESC_MAX)


if __name__ == "__main__":
    unittest.main()
