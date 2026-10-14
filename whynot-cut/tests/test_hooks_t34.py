"""3.0 Phase 3 T3.4 hooks: the `if` filters of the file tools (a write outside client sources starts no process), the
CwdChanged context (handed over by the guard), the first-run nudge, panel approvals / change requests, pending updates,
busy clients, ~/.whynot-cut/plugin-root.json, the fallback word split (T2.5 carry-over), the optional Stop evidence
gate and the writer lease across /clear (same Claude Code process, new session id). Hook tests feed JSON on stdin.
Run:  tools/test.sh -p test_hooks_t34.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from test_plugin import CTX, GUARD, SK, ClientFixture, hook, mark_client

sys.path.insert(0, str(SK / "engine" / "reel"))
from lib import writer_lock  # noqa: E402

END = SK / "hooks" / "session_end.py"
STOP_PY = SK / "hooks" / "stop_gate.py"
STOP_SH = SK / "hooks" / "stop_gate.sh"
HOOKS = json.loads((SK / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
SESSION_ENV = ("WHYNOT_LOCK_SESSION", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = load(CTX, "session_context_t34")


def no_session_env(**extra) -> dict:
    """The hook environment without the developer's own Claude session ids (the tests set what they need)."""
    e = {k: "" for k in SESSION_ENV}
    e.update(extra)
    return e


def ctx_of(out: str) -> str:
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else ""


class HookFixture(ClientFixture):
    def setUp(self):
        super().setUp()
        self.data = Path(self.tmp.name) / "pdata"
        self.data.mkdir()
        self.home = Path(self.tmp.name) / "engine-home"
        self.home.mkdir()

    def env(self, **extra):
        e = no_session_env(CLAUDE_PLUGIN_DATA=str(self.data), WHYNOT_HOME=str(self.home),
                           WHYNOT_OPTIONS_FILE=str(Path(self.tmp.name) / "wnc" / "plugin-options.json"))
        e.update(extra)
        return e

    def start(self, cwd, sid="s1", **extra):
        code, out, err = hook(CTX, {"hook_event_name": "SessionStart", "source": "startup", "session_id": sid,
                                    "cwd": str(cwd)}, self.env(**extra))
        self.assertEqual(code, 0, err)
        return ctx_of(out)

    def cwd_changed(self, old, new, sid="s1", **extra):
        code, out, err = hook(CTX, {"hook_event_name": "CwdChanged", "session_id": sid, "cwd": str(old),
                                    "old_cwd": str(old), "new_cwd": str(new)}, self.env(**extra))
        self.assertEqual(code, 0, err)
        return json.loads(out) if out.strip() else None

    def pending(self, sid="s1") -> Path:
        return self.data / "pending-context" / sid


# ------------------------------------------------------------------------------------------------------ if filters
class TestFileToolIfFilter(ClientFixture):
    def test_hooks_json_runs_the_guard_per_tool_and_pattern(self):
        groups = {g["matcher"]: g["hooks"] for g in HOOKS["PreToolUse"]}
        self.assertEqual(set(groups), {"Bash|PowerShell", "Write|Edit|NotebookEdit", "MultiEdit"})
        for m in ("Bash|PowerShell", "MultiEdit"):          # always guarded, never filtered
            self.assertEqual([h.get("if") for h in groups[m]], [None])
        files = groups["Write|Edit|NotebookEdit"]
        self.assertEqual([h["if"] for h in files], [f"{t}({p})" for t in SC.FILE_IF_TOOLS for p in SC.FILE_IF_PATTERNS])
        self.assertEqual(set(SC.FILE_IF_TOOLS), set("Write|Edit|NotebookEdit".split("|")))
        for h in [h for g in groups.values() for h in g]:
            self.assertIn("hooks/guard.py", h["command"])
            self.assertEqual(h["timeout"], 10)
        self.assertEqual(set(SC.GUARDED_TOOLS), {t for m in groups for t in m.split("|")})

    def test_every_write_the_guard_blocks_matches_the_filter(self):
        ae = Path(self.tmp.name) / "Roaming" / "Adobe" / "After Effects" / "25.0" / "Adobe After Effects 25.0 Prefs.txt"
        blocked = [("Write", self.root / "data/Raw/new.txt", None), ("Edit", self.root / "assets/Photos/x.png", None),
                   ("Write", self.root / "DATA/Raw/x.txt", None), ("Write", self.root / "Assets/new.png", None),
                   ("Write", self.root / ".whynot-client", None), ("NotebookEdit", self.root / "data/n.ipynb", None),
                   ("Write", self.root / "output/.whynot-lock", "whynot-cut:story-editor"),
                   ("Edit", self.root / "output/.whynot-lock.stale-12", "whynot-cut:story-editor"),
                   ("Write", ae, None)]
        for tool, p, agent in blocked:
            with self.subTest(path=str(p)):
                key = "notebook_path" if tool == "NotebookEdit" else "file_path"
                payload = {"tool_name": tool, "cwd": "/", "tool_input": {key: str(p)}}
                if agent:
                    payload["agent_type"] = agent
                self.assertEqual(hook(GUARD, payload)[0], 2)
                self.assertTrue(SC.file_guarded(str(p)))
                self.assertTrue(SC.file_guarded(str(p).replace("/", "\\")))
        other = Path(self.tmp.name) / "repo"
        allowed = [self.root / "output/projects/C0001/x.json", self.root / "output/notes.md", other / "src/a.py",
                   other / "mydata/x.txt", other / "database/y.txt", other / "assets2/z.txt",
                   Path(self.tmp.name) / "Adobe" / "Premiere Pro" / "x.txt"]
        for p in allowed:
            with self.subTest(path=str(p)):
                self.assertEqual(hook(GUARD, {"tool_name": "Write", "cwd": "/", "tool_input": {"file_path": str(p)}})[0], 0)
                self.assertFalse(SC.file_guarded(str(p)), "an ordinary write would start the guard")

    def test_read_only_reviewers_have_no_file_tools(self):
        """The guard's role rule (read-only reviewers never edit) needs no path-free file hook: those agents have no
        Write/Edit/MultiEdit/NotebookEdit tool at all."""
        g = load(GUARD, "guard_t34")
        for name in sorted(g.READ_ONLY_AGENTS):
            text = (SK / "agents" / f"{name}.md").read_text(encoding="utf-8")
            m = re.search(r"^tools:\s*(.*)$", text.split("\n---", 1)[0], re.M)
            self.assertIsNotNone(m, f"{name}: tools must be listed (no list = every tool)")
            tools = set(re.findall(r"[A-Za-z]+", m.group(1)))
            self.assertFalse(tools & {"Write", "Edit", "MultiEdit", "NotebookEdit"}, name)


def _stamp(at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _call(name: str, at: float, **inp) -> str:
    return json.dumps({"type": "assistant", "timestamp": _stamp(at), "message": {
        "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_x", "name": name, "input": inp}]}})


class TestHeartbeatFollowsTheFilter(HookFixture):
    """A Write the `if` filter skips never reaches the guard, so no heartbeat is expected for it: no false alarm."""

    def run_session(self, *lines):
        tdir = Path(self.tmp.name) / "t"
        tdir.mkdir(exist_ok=True)
        start = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.root)}
        hook(CTX, dict(start, session_id="a", transcript_path=str(tdir / "a.jsonl")), self.env())
        user = json.dumps({"type": "user", "timestamp": _stamp(time.time()), "message": {"role": "user", "content": "x"}})
        (tdir / "a.jsonl").write_text("\n".join([user, *lines]) + "\n", encoding="utf-8")
        _, out, _ = hook(CTX, dict(start, session_id="b", transcript_path=str(tdir / "b.jsonl")), self.env())
        return ctx_of(out)

    def test_write_outside_sources_is_no_alarm(self):
        now = time.time()
        self.assertNotIn("protection may be OFF",
                         self.run_session(_call("Write", now, file_path=str(self.root / "output/x.md")),
                                          _call("Edit", now, file_path="C:\\work\\repo\\src\\a.py")))

    def test_write_into_sources_without_a_heartbeat_warns(self):
        self.assertIn("protection may be OFF",
                      self.run_session(_call("Write", time.time(), file_path=str(self.root / "data/Raw/x.txt"))))


# ------------------------------------------------------------------------------------------------------ CwdChanged
class TestCwdChanged(HookFixture):
    def test_same_context_as_session_start_handed_over_by_the_guard(self):
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        want = self.start(self.root, sid="ref")                 # what SessionStart says for this folder
        self.assertIn("this is a client folder", want)
        msg = self.cwd_changed(outside, self.root)
        self.assertEqual(set(msg), {"systemMessage"})          # CwdChanged reads only systemMessage / watchPaths
        self.assertIn("example clinic", msg["systemMessage"])
        self.assertEqual(self.pending().read_text(encoding="utf-8"), want)
        self.assertEqual((self.data / "scope" / "s1").read_text(encoding="utf-8"), str(self.root))
        # the guard hands it over with the lead's next Bash call, once; never to a subagent
        bash = {"tool_name": "Bash", "tool_input": {"command": "ls output"}, "cwd": str(self.root), "session_id": "s1"}
        code, out, _ = hook(GUARD, dict(bash, agent_type="whynot-cut:story-editor"), self.env())
        self.assertEqual((code, out), (0, ""))
        code, out, _ = hook(GUARD, bash, self.env())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": want}})
        self.assertFalse(self.pending().exists())
        self.assertEqual(hook(GUARD, bash, self.env())[1], "")
        # a blocked call keeps it waiting
        self.cwd_changed(self.root, outside)
        self.cwd_changed(outside, self.root)
        code, out, _ = hook(GUARD, dict(bash, tool_input={"command": "rm -rf data"}), self.env())
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(self.pending().exists())

    def test_said_once_per_place(self):
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        self.start(self.root)                                   # SessionStart already told this session
        self.assertIsNone(self.cwd_changed(self.root, self.root / "output/projects/C0001"))
        self.assertFalse(self.pending().exists())
        self.assertIsNone(self.cwd_changed(self.root, outside))  # leaving: nothing to say, the place is forgotten
        self.assertFalse((self.data / "scope" / "s1").exists())
        self.assertIsNotNone(self.cwd_changed(outside, self.root / "data"))   # back in: said again
        self.assertTrue(self.pending().exists())

    def test_leaving_clears_the_waiting_context_and_follows_the_evidence_gate(self):
        """Fix round 1 (M4): a context for a client the session already left is never handed over later, and the
        evidence-gate flag follows the folder (it was written only at SessionStart)."""
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        prefs = self.root / ".claude" / "whynot-cut.local.md"
        prefs.parent.mkdir()
        prefs.write_text("---\nevidence_gate: on\n---\n", encoding="utf-8")
        gate = self.data / "evidence-gate" / "s1"
        self.start(outside)
        self.assertFalse(gate.exists())
        self.cwd_changed(outside, self.root)                    # into a client with the gate on
        self.assertTrue(self.pending().exists())
        self.assertTrue(gate.is_file())
        self.assertIsNone(self.cwd_changed(self.root, outside))  # left before any Bash call
        self.assertFalse(self.pending().exists(), "a stale context for the old client would be handed over later")
        self.assertFalse(gate.exists())
        self.cwd_changed(outside, self.root)
        prefs.write_text("---\nevidence_gate: on\napproval: auto\n---\n", encoding="utf-8")
        self.cwd_changed(self.root, self.root / "output")        # same client, preferences changed: flag follows
        self.assertFalse(gate.exists())

    def test_unrelated_folders_stay_silent_and_session_end_cleans_up(self):
        a, b = Path(self.tmp.name) / "a", Path(self.tmp.name) / "b"
        a.mkdir()
        b.mkdir()
        self.start(a)                                           # (the first-run nudge at most)
        self.assertIsNone(self.cwd_changed(a, b))
        self.assertEqual(sorted(p.name for p in self.data.rglob("*") if p.is_file()),
                         ["first-run-done", "last-session-start"])
        self.cwd_changed(a, self.root)
        p = {"hook_event_name": "SessionEnd", "reason": "clear", "session_id": "s1", "cwd": str(a)}
        r = subprocess.run([sys.executable, str(END)], input=json.dumps(p), capture_output=True, text=True,
                           encoding="utf-8", env=dict(os.environ, **self.env()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.pending().exists())
        self.assertFalse((self.data / "scope" / "s1").exists())

    def test_hooks_json_wires_cwdchanged_like_session_start(self):
        (start,), (cwd,) = HOOKS["SessionStart"], HOOKS["CwdChanged"]
        self.assertEqual(start["hooks"], cwd["hooks"])
        self.assertNotIn("matcher", cwd)                        # CwdChanged has no matcher support
        self.assertEqual(start["matcher"].split("|"), ["startup", "resume", "clear", "compact", "fork"])


# ------------------------------------------------------------------------------------------------------ first run
class TestFirstRunNudge(HookFixture):
    def test_nudge_once_then_silence(self):
        a = Path(self.tmp.name) / "unrelated"
        a.mkdir()
        first = self.start(a)
        self.assertIn("/whynot-cut:start", first)
        self.assertIn("once", first)
        self.assertTrue((self.data / "first-run-done").is_file())
        self.assertEqual(self.start(a, sid="s2"), "")

    def test_no_plugin_data_no_nudge(self):
        a = Path(self.tmp.name) / "unrelated"
        a.mkdir()
        code, out, _ = hook(CTX, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(a)},
                            no_session_env(WHYNOT_HOME=str(self.home)))
        self.assertEqual((code, out), (0, ""))

    def test_first_start_in_a_client_folder_needs_no_extra_nudge(self):
        ctx = self.start(self.root)
        self.assertIn("not installed (run /whynot-cut:start)", ctx)
        self.assertNotIn("just installed", ctx)
        self.assertTrue((self.data / "first-run-done").is_file())


# ------------------------------------------------------------------------------------------------------ pending lists
class TestPendingLists(HookFixture):
    def item(self, vid="C0001") -> Path:
        d = self.root / "output/projects" / vid
        (d / "01_analysis").mkdir(parents=True, exist_ok=True)
        return d

    def test_panel_approval_until_built(self):
        d = self.item()
        now = datetime.now().astimezone()
        (d / "01_analysis/plan-approval.json").write_text(json.dumps(
            {"approved": True, "by": "editor", "via": "panel", "editor_name": "Yunus", "at": now.isoformat()}),
            encoding="utf-8")
        ctx = self.start(self.root)
        self.assertIn(f"Yunus approved C0001 in Premiere at {now.strftime('%H:%M')}", ctx)
        (d / "07_premiere").mkdir()
        (d / "07_premiere/ppro-build-result.json").write_text("{}", encoding="utf-8")
        self.assertNotIn("approved C0001", self.start(self.root, sid="s2"))
        (self.item("C0002") / "01_analysis/plan-approval.json").write_text(
            json.dumps({"approved": True, "by": "editor", "at": now.isoformat()}), encoding="utf-8")
        self.assertNotIn("in Premiere", self.start(self.root, sid="s3"))     # approved in chat: nothing to report

    def test_change_requests_from_the_panel(self):
        d = self.item()
        (d / "panel-requests.json").write_text(json.dumps([
            {"text": "old", "at": "2026-10-12T10:00:00+03:00", "done": True},
            {"text": "make the  title\nbigger", "at": "2026-10-13T10:00:00+03:00"}]), encoding="utf-8")
        (self.item("C0002") / "panel-requests.json").write_text(json.dumps(
            {"requests": [{"text": "x", "status": "resolved"}]}), encoding="utf-8")
        (self.item("C0003") / "panel-requests.json").write_text("not json", encoding="utf-8")
        ctx = self.start(self.root)
        self.assertIn("Change requests from the Premiere panel waiting: C0001 (1, latest: “make the title bigger”)", ctx)
        self.assertNotIn("C0002 (", ctx)
        self.assertNotIn("C0003 (", ctx)

    def test_pending_updates_from_state_json(self):
        comp = json.loads((SK / "setup/components.json").read_text(encoding="utf-8"))
        self.assertNotIn("Updates pending", self.start(self.root))          # no state.json: silent
        (self.home / "state.json").write_text(json.dumps(
            {"schema": 1, "plugin": "2.2.1", "ffmpeg": {"version": "0.0.1"},
             "fonts": {"version": comp["fonts"]["version"]}, "runtime": {"id": "anything"}, "steps": {}}),
            encoding="utf-8")
        ctx = self.start(self.root, sid="s2")
        self.assertIn(f"Updates pending (plugin 2.2.1 → {comp['plugin']}, ffmpeg 0.0.1 → {comp['ffmpeg']['version']})",
                      ctx)                                   # runtime id "<release>" in components: never compared
        self.assertNotIn("fonts", ctx.split("Updates pending", 1)[1].split(")", 1)[0])

    def test_clients_folder_lists_busy_clients_and_panel_items(self):
        base = Path(self.tmp.name)
        other = base / "second clinic"
        for x in ("assets", "data", "output"):
            (other / x).mkdir(parents=True)
        mark_client(other)
        rec = {"session_id": "someone-else", "pid": os.getpid(), "pid_created": writer_lock.process_created(os.getpid()),
               "host": socket.gethostname(), "host_id": writer_lock.host_id(), "started_at": "2026-10-13T09:00:00+03:00",
               "command": "reel transcribe --video-id C0009"}
        (other / "output/.whynot-lock").write_text(json.dumps(rec), encoding="utf-8")
        (self.item() / "panel-requests.json").write_text(json.dumps([{"text": "cut the intro"}]), encoding="utf-8")
        ctx = self.start(base, WHYNOT_CLIENTS_ROOT=str(base))
        self.assertIn("this is the clients folder", ctx)
        self.assertIn("Busy (another session holds the client, do not write there): second clinic "
                      "(reel transcribe --video-id C0009", ctx)
        self.assertNotIn("example clinic (", ctx.split("Busy", 1)[1].split(". ", 1)[0])
        self.assertIn("[example clinic] Change requests from the Premiere panel waiting: C0001", ctx)

    # fix round 1 (I1): the panel's only location, and one time budget for the clients-folder lists
    def test_change_requests_are_read_at_the_item_level_only(self):
        (self.item("C0001") / "panel-requests.json").write_text(json.dumps([{"text": "here"}]), encoding="utf-8")
        for rel in ("output/projects/C0002/01_analysis/panel-requests.json", "output/other/panel-requests.json",
                    "output/projects/panel-requests.json"):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps([{"text": "not here"}]), encoding="utf-8")
        ctx = self.start(self.root)
        self.assertIn("Change requests from the Premiere panel waiting: C0001 (1, latest: “here”)", ctx)
        self.assertNotIn("not here", ctx)
        self.assertEqual(SC.REQUEST_GLOBS, ("output/projects/*/panel-requests.json",))

    def test_clients_folder_lists_share_one_time_budget(self):
        names = [f"client {i:02d}" for i in range(60)]
        calls = []

        def slow(root):
            calls.append(root.name)
            time.sleep(0.02)
            return "Change requests from the Premiere panel waiting: C0001 (1). "
        t0 = time.monotonic()
        with mock.patch.object(SC, "panel_line", slow):
            line = SC.clients_lists(Path(self.tmp.name), names, budget=0.2)
        took = time.monotonic() - t0
        self.assertLess(took, 0.6, "the budget must bound the whole scan")
        self.assertLess(len(calls), 60)
        self.assertIn(f"(scan cut short: {60 - len(calls)} of 60 clients not checked for panel approvals or change "
                      f"requests)", line)
        self.assertIn("[client 00] Change requests", line)
        with mock.patch.object(SC, "panel_line", lambda root: ""):
            self.assertNotIn("cut short", SC.clients_lists(Path(self.tmp.name), names))

    # fix round 2 (m1, m2): leases and the re-key for every client first, the panel scan under the budget after;
    # the note counts all clients
    def test_leases_and_rekey_are_never_skipped_by_the_time_budget(self):
        base = Path(self.tmp.name) / "many"
        names = [f"c{i:03d}" for i in range(80)]                 # more than 60, the own lease in the very last one
        for n in names:
            for d in ("assets", "data", "output"):
                (base / n / d).mkdir(parents=True)
            mark_client(base / n)
        me = os.getppid()
        env = {"WHYNOT_LOCK_SESSION": "A", "CLAUDE_PID": str(me)}
        with mock.patch.dict(os.environ, {}):
            for k in SESSION_ENV:
                os.environ.pop(k, None)
            writer_lock.acquire(base / names[-1], "reel transcribe", env).release()
            other = dict(writer_lock.read(base / names[-1]), session_id="someone-else", pid=os.getpid(),
                         pid_created=writer_lock.process_created(os.getpid()), host=socket.gethostname(),
                         host_id=writer_lock.host_id())
            (base / names[-2] / "output/.whynot-lock").write_text(json.dumps(other), encoding="utf-8")

        def slow(root):
            time.sleep(0.02)
            return ""
        payload = {"hook_event_name": "SessionStart", "source": "clear", "session_id": "B", "cwd": str(base)}
        with mock.patch.object(SC, "panel_line", slow),                 mock.patch.dict(SC.DATA, payload), mock.patch.dict(os.environ, {"CLAUDE_PID": str(me)}):
            line = SC.clients_lists(base, names, budget=0.1)
        self.assertEqual(writer_lock.read(base / names[-1])["session_id"], "B")      # re-keyed after the cut-off
        self.assertIn(f"{names[-2]} (", line)                                          # busy list covers every client
        self.assertNotIn(f"{names[-1]} (", line)
        m = re.search(r"scan cut short: (\d+) of 80 clients", line)                   # m2: all 80 counted
        self.assertTrue(m and 0 < int(m.group(1)) < 80, line)

    def test_clients_folder_scan_on_a_big_tree(self):
        """60 clients x 30 items with stage folders (the old depth-3 glob walked every stage folder of every item)."""
        base = Path(self.tmp.name) / "big"
        names = [f"c{i:02d}" for i in range(60)]
        for n in names:
            for j in range(30):
                for stage in ("01_analysis/x", "07_premiere/frames", "08_qc/sheets"):
                    (base / n / "output/projects" / f"C{j:04d}" / stage).mkdir(parents=True)
        (base / "c59/output/projects/C0007/panel-requests.json").write_text(json.dumps([{"text": "late"}]),
                                                                            encoding="utf-8")
        t0 = time.monotonic()
        line = SC.clients_lists(base, names)
        took = time.monotonic() - t0
        self.assertLess(took, SC.CLIENT_SCAN_BUDGET_S + 0.5, f"{took:.2f}s")
        self.assertTrue("[c59] Change requests" in line or "scan cut short" in line, line)


class TestPluginRootFile(HookFixture):
    def test_written_by_a_real_hook_run_only_when_changed(self):
        f = Path(self.tmp.name) / "wnc" / "plugin-root.json"
        self.start(self.root)                                   # no CLAUDE_PLUGIN_ROOT: a bare run writes nothing
        self.start(self.root, sid="s1b", CLAUDE_PLUGIN_ROOT=str(SK))    # no CLAUDE_ENV_FILE: not a real SessionStart
        self.assertFalse(f.exists())
        self.assertFalse(f.parent.exists(), "a bare run must not create the engine home's folder")
        real = {"CLAUDE_PLUGIN_ROOT": str(SK), "CLAUDE_ENV_FILE": str(Path(self.tmp.name) / "env.sh")}
        self.start(self.root, sid="s2", **real)
        rec = json.loads(f.read_text(encoding="utf-8"))
        version = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual((rec["root"], rec["version"]), (str(SK), version))
        self.assertRegex(rec["at"], r"^\d{4}-\d\d-\d\dT")
        before = f.read_bytes()
        os.utime(f, (1, 1))
        self.start(self.root, sid="s3", **real)
        self.assertEqual((f.read_bytes(), f.stat().st_mtime), (before, 1))      # unchanged: not rewritten


# ------------------------------------------------------------------------------------------------------ fallback words
class TestFallbackWordSplit(ClientFixture):
    def test_arabic_glued_to_a_latin_hint_is_one_word(self):
        self.assertNotIn("ref", SC._words("data/مقابلةref.mp4"))
        self.assertIn("ref", SC._words("data/مقابلة ref.mp4"))
        self.assertIn("ref", SC._words("data/Style ref1.mp4"))
        self.assertIn("raw", SC._words("data/RawTake.mp4"))
        self.assertIn("ref", SC._folder_words("مراجعref"))      # folders: as discover.folder_kind reads them

    def test_fallback_agrees_with_classify_on_arabic_names(self):
        from lib.discover import classify
        files = ["data/مقابلةref.mp4", "data/مقابلة ref.mp4", "data/Raw/مقابلة.mp4", "data/حلقةRaw/a.mp4",
                 "data/مقابلة_stock.mp4", "data/لقاءbroll.mp4"]
        for rel in files:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(b"x")
        rels = ["data/Raw/C0001.MP4"] + files
        want = [Path(r).stem for r in rels if classify(self.root / r, r)["role"] == "source_footage"]
        self.assertIn("مقابلةref", want)
        with mock.patch("lib.discover.classify", side_effect=RuntimeError("engine unavailable")):
            got = SC.new_clips(self.root)
        norm = lambda x: "".join(c if c.isascii() and c.isalnum() else "_" for c in x).strip("_").upper() or "VIDEO"
        self.assertEqual(sorted(got), sorted(norm(w) for w in want))
        self.assertIn("REF", got)                               # data/مقابلةref.mp4 is a new clip, not a reference


# ------------------------------------------------------------------------------------------------------ Stop gate
class TestEvidenceGate(HookFixture):
    def turn(self, *cmds, user="make the reel") -> str:
        t = Path(self.tmp.name) / "turn.jsonl"
        lines = [json.dumps({"type": "user", "timestamp": _stamp(time.time() - 60),
                             "message": {"role": "user", "content": "earlier"}}),
                 _call("Bash", time.time(), command="reel qc --video-id OLD"),       # an earlier turn's qc
                 json.dumps({"type": "user", "timestamp": _stamp(time.time()),
                             "message": {"role": "user", "content": user}})]
        lines += [_call("Bash", time.time(), command=c) for c in cmds]
        lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_x", "content": "ok"}]}}))
        t.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(t)

    def gate(self, msg, transcript, active=False):
        r = subprocess.run([sys.executable, str(STOP_PY)], input=json.dumps(
            {"hook_event_name": "Stop", "stop_hook_active": active, "last_assistant_message": msg,
             "transcript_path": transcript}), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_ready_claim_without_qc_is_sent_back_once(self):
        t = self.turn("reel --root . ppro-build --video-id C0001")
        out = self.gate("The reel is ready for review in Premiere.", t)
        self.assertEqual(out["decision"], "block")
        self.assertIn("reel qc", out["reason"])
        self.assertIsNotNone(self.gate("الريل جاهز يا يونس", t))
        self.assertIsNone(self.gate("The reel is ready for review.", t, active=True))      # never loops

    def test_no_block_with_proof_without_claim_or_without_reel_work(self):
        self.assertIsNone(self.gate("It is done.", self.turn("reel ppro-build", "reel --root . qc --video-id C0001")))
        self.assertIsNone(self.gate("All set.", self.turn("reel verify --video-id C0001")))
        self.assertIsNone(self.gate("I built it; the frames still need a look.", self.turn("reel ppro-build")))
        self.assertIsNone(self.gate("The fix is done.", self.turn("git status", "npm test")))
        self.assertIsNone(self.gate("Done.", str(Path(self.tmp.name) / "missing.jsonl")))

    def test_off_by_default_and_on_by_preference(self):
        self.start(self.root)
        self.assertFalse((self.data / "evidence-gate" / "s1").exists())
        prefs = self.root / ".claude" / "whynot-cut.local.md"
        prefs.parent.mkdir()
        prefs.write_text("---\nevidence_gate: on\n---\n", encoding="utf-8")
        self.start(self.root)
        self.assertTrue((self.data / "evidence-gate" / "s1").is_file())
        prefs.write_text("---\nevidence_gate: on\napproval: auto\n---\n", encoding="utf-8")
        self.start(self.root)
        self.assertFalse((self.data / "evidence-gate" / "s1").exists())     # autopilot with delegated approval: off

    @unittest.skipUnless(shutil.which("bash"), "bash not found")
    def test_stop_hook_without_the_flag_starts_no_python(self):
        """stop_gate.sh decides with bash builtins: off = no Python; on = the gate runs."""
        t = self.turn("reel ppro-build")
        payload = json.dumps({"hook_event_name": "Stop", "last_assistant_message": "It is ready.", "transcript_path": t})
        env = dict(os.environ, **self.env(CLAUDE_CODE_SESSION_ID="s1"))
        stamp = self.data / "hooks-ok"                          # run_python.sh touches it whenever it starts Python
        r = subprocess.run([shutil.which("bash"), str(STOP_SH)], input=payload, capture_output=True, text=True,
                           encoding="utf-8", env=env)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        self.assertFalse(stamp.exists())
        (self.data / "evidence-gate").mkdir()
        (self.data / "evidence-gate" / "s1").write_text("on\n", encoding="utf-8")
        r = subprocess.run([shutil.which("bash"), str(STOP_SH)], input=payload, capture_output=True, text=True,
                           encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["decision"], "block")
        self.assertTrue(stamp.exists())

    def test_hooks_json_stop_entry(self):
        (stop,) = HOOKS["Stop"]
        (h,) = stop["hooks"]
        self.assertEqual((h["type"], h["timeout"]), ("command", 30))
        self.assertIn("hooks/stop_gate.sh", h["command"])

    # fix round 1 (M1): the subcommand by shlex, skipping only the global options that take a value
    def test_reel_subcommand_parsing(self):
        SG = load(STOP_PY, "stop_gate_t34")
        cases = {
            'reel --root "Test Clinic" qc --video-id C1': [("qc", "C1")],
            "reel --root 'عيادة تجربة' ppro-build --video-id C0001": [("ppro-build", "C0001")],
            "reel --json qc C1": [("qc", None)],
            '"$WHYNOT_HOME/bin/reel" qc --video-id=C7': [("qc", "C7")],
            '& "C:\\Users\\x\\.whynot-cut\\bin\\reel.cmd" --root "D:\\Clients\\A B" verify --video-id C2': [("verify", "C2")],
            "cd out && reel --video-id C3 status; reel qc": [("status", "C3"), ("qc", None)],
            "reel": [], "echo reel qc": [], "git status": [], "preel qc": [],
            # fix round 2 (m3): one level of shell / launcher
            "bash -lc \"reel --root 'D:/A B' qc --video-id C5\"": [("qc", "C5")],
            "sh -c 'reel qc'": [("qc", None)],
            "cmd /c reel --video-id C6 qc": [("qc", "C6")],
            'cmd.exe /d /s /c "reel.cmd qc --video-id C8"': [("qc", "C8")],
            'powershell -Command "reel verify --video-id C9"': [("verify", "C9")],
            "powershell.exe -NoProfile -Command \"& 'C:\\x\\reel.cmd' qc\"": [("qc", None)],
            'pwsh -c "reel qc; reel status"': [("qc", None), ("status", None)],
            "timeout 60 reel qc": [("qc", None)],
            "timeout -s KILL 2.5m reel --video-id C4 qc": [("qc", "C4")],
            'bash -lc "echo reel qc"': [], "bash script.sh --check reel qc": [],
            "bash -c \"bash -c 'reel qc'\"": [],                     # one level only
        }
        for cmd, want in cases.items():
            with self.subTest(cmd=cmd):
                self.assertEqual(SG.reel_calls(cmd), want)

    def test_quoted_and_wrapped_reel_commands_are_judged(self):
        t = self.turn('reel --root "Test Clinic" ppro-build --video-id C0001')
        self.assertIsNotNone(self.gate("It is ready.", t))
        self.assertIsNone(self.gate("It is ready.", self.turn('reel --root "Test Clinic" ppro-build --video-id C0001',
                                                              'reel --root "Test Clinic" qc --video-id C0001')))
        t = self.turn('"$WHYNOT_HOME/bin/reel" ppro-build --video-id C0001')
        self.assertIsNotNone(self.gate("It is ready.", t))                 # was never seen: the gate did not fire
        self.assertIsNone(self.gate("It is ready.", self.turn('"$WHYNOT_HOME/bin/reel" ppro-build',
                                                              "reel --json qc C0001")))

    def test_wrapped_commands_fire_the_gate_and_count_as_proof(self):
        t = self.turn("bash -lc \"reel ppro-build --video-id C0001\"")
        self.assertIsNotNone(self.gate("It is ready.", t))
        for qc in ("bash -lc \"reel qc --video-id C0001\"", "cmd /c reel qc --video-id C0001",
                   "powershell -Command \"reel qc --video-id C0001\"", "timeout 60 reel qc --video-id C0001"):
            with self.subTest(qc=qc):
                self.assertIsNone(self.gate("It is ready.", self.turn("reel ppro-build --video-id C0001", qc)))

    # fix round 1 (M2): proof from this turn's subagents, and from earlier turns for the same item
    def test_qc_run_by_a_subagent_this_turn_counts(self):
        t = Path(self.turn("reel ppro-build --video-id C0001"))
        sub = t.with_suffix("") / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-q.jsonl").write_text("\n".join([
            json.dumps({"type": "user", "isSidechain": True, "message": {"role": "user", "content": "check C0001"}}),
            _call("Bash", time.time(), command="reel --root . qc --video-id C0001")]) + "\n", encoding="utf-8")
        self.assertIsNone(self.gate("The reel is ready for review.", str(t)))
        old = time.time() - 3600                                       # a subagent of an earlier turn: no proof
        os.utime(sub / "agent-q.jsonl", (old, old))
        self.assertIsNotNone(self.gate("The reel is ready for review.", str(t)))

    def test_earlier_turn_proof_for_the_same_item(self):
        def session(*turns):
            t = Path(self.tmp.name) / "multi.jsonl"
            lines = []
            for i, cmds in enumerate(turns):
                lines.append(json.dumps({"type": "user", "timestamp": _stamp(time.time() - 100 + i),
                                         "message": {"role": "user", "content": f"turn {i}"}}))
                lines += [_call("Bash", time.time() - 100 + i, command=c) for c in cmds]
            t.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return str(t)
        built = ["reel ppro-build --video-id C0001", "reel qc --video-id C0001"]
        self.assertIsNone(self.gate("Yes, it is ready.", session(built, ["reel status --video-id C0001"])))
        self.assertIsNone(self.gate("Yes, it is ready.", session(built, ["reel next"])))
        self.assertIsNotNone(self.gate("It is ready.", session(built, ["reel status --video-id C0002"])))   # other item
        self.assertIsNotNone(self.gate("It is ready.", session(built, ["reel ppro-build --video-id C0001"])))  # rebuilt
        self.assertIsNotNone(self.gate("It is ready.", session(built + ["reel plan --video-id C0001"],
                                                                ["reel status --video-id C0001"])))     # changed since

    def test_evidence_gate_is_a_known_preference(self):
        sys.path.insert(0, str(SK / "engine" / "reel" / "lib"))
        import settings as S
        self.assertIs(S.DEFAULTS["evidence_gate"], False)
        self.assertIn("| `evidence_gate` |", (SK / "skills/preferences/SKILL.md").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------ /clear lease
class TestLeaseAcrossClear(unittest.TestCase):
    """Seen live (docs/superpowers/evidence/2026-10-13-t3.4-session-ids.md): /clear ends session A and starts B in the
    same Claude Code process (CLAUDE_PID unchanged); Bash then sees CLAUDE_CODE_SESSION_ID=B. A's lease must never
    lock B out of its own client, even when SessionEnd did not get to release it: SessionStart (source clear or resume,
    same CLAUDE_PID) re-keys it to B (fix round 1, M3); nothing else does."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "lease clinic"
        for d in ("assets", "data", "output"):
            (self.root / d).mkdir(parents=True)
        mark_client(self.root)
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {})                # acquire() sets WHYNOT_LOCK_SESSION in os.environ
        patcher.start()
        self.addCleanup(patcher.stop)
        for k in SESSION_ENV:
            os.environ.pop(k, None)

        self.claude = os.getppid()                               # stands in for the session's Claude Code process
        self.other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])   # another live one
        self.addCleanup(self.other.wait)
        self.addCleanup(self.other.kill)

    def env(self, sid, pid):
        return {"WHYNOT_LOCK_SESSION": sid, "CLAUDE_PID": str(pid)}

    def start(self, source, sid, cwd=None, pid=None, **extra):
        payload = {"hook_event_name": "SessionStart", "source": source, "session_id": sid,
                   "cwd": str(cwd or self.root)}
        code, out, err = hook(CTX, payload, no_session_env(CLAUDE_PID=str(pid or self.claude), **extra))
        self.assertEqual(code, 0, err)
        return ctx_of(out)

    def test_a_new_session_id_in_the_same_process_is_refused_until_session_start(self):
        """Fix round 1 (M3): the takeover is no longer "any new session id in the same process" (teammates of an agent
        team could pass the lease back and forth); between SessionStarts the T1.8 refusal stands."""
        me = self.claude
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", me)).release()
        with self.assertRaises(writer_lock.Busy):
            writer_lock.acquire(self.root, "reel plan", self.env("B", me))
        self.assertFalse(writer_lock.status(self.root, self.env("B", me))["mine"])
        with mock.patch.dict(os.environ, {"CLAUDE_PID": str(me)}):
            self.assertIsNotNone(writer_lock.other_writer(self.root, "B"))
        self.assertEqual(writer_lock.read(self.root)["session_id"], "A")

    def test_session_start_after_clear_or_resume_continues_the_lease(self):
        me = self.claude
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", me)).release()
        self.assertNotIn("another session is working in this client", self.start("clear", "B"))
        rec = writer_lock.read(self.root)
        self.assertEqual((rec["session_id"], rec["command"], rec["pid"]), ("B", "reel transcribe", me))
        log = (self.root / "output/logs/pipeline.log").read_text(encoding="utf-8")
        self.assertIn("session B continues the lease of session A (same Claude Code process", log)
        writer_lock.acquire(self.root, "reel plan", self.env("B", me)).release()          # B writes on
        self.assertEqual(writer_lock.read(self.root)["command"], "reel plan")
        self.assertTrue(writer_lock.status(self.root, self.env("B", me))["mine"])
        self.start("resume", "C")
        self.assertEqual(writer_lock.read(self.root)["session_id"], "C")

    def test_other_session_starts_never_take_the_lease(self):
        me = self.claude
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", me)).release()
        for source in ("startup", "compact", "fork"):
            with self.subTest(source=source):
                self.assertIn("another session is working in this client", self.start(source, "B"))
                self.assertEqual(writer_lock.read(self.root)["session_id"], "A")
        self.assertIn("another session is working in this client", self.start("clear", "B", pid=self.other.pid))
        self.assertEqual(writer_lock.read(self.root)["session_id"], "A")                  # another process

    def test_session_start_after_clear_in_the_clients_folder(self):
        me = self.claude
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", me)).release()
        base = self.root.parent
        ctx = self.start("clear", "B", cwd=base, WHYNOT_CLIENTS_ROOT=str(base))
        self.assertIn("this is the clients folder", ctx)
        self.assertNotIn("Busy", ctx)
        self.assertEqual(writer_lock.read(self.root)["session_id"], "B")

    def test_another_claude_process_is_still_another_writer(self):
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", self.claude)).release()
        other = self.other.pid                                   # alive, but not the lease holder
        with self.assertRaises(writer_lock.Busy):
            writer_lock.acquire(self.root, "reel plan", self.env("B", other))
        self.assertFalse(writer_lock.rekey(self.root, "B", self.env("B", other)))         # never another process
        self.assertFalse(writer_lock.status(self.root, self.env("B", other))["mine"])
        with mock.patch.dict(os.environ, {"CLAUDE_PID": str(other)}):
            self.assertIsNotNone(writer_lock.other_writer(self.root, "B"))
        rec = dict(writer_lock.read(self.root), pid_created="1")                # same pid, other process start
        self.assertFalse(writer_lock.same_process(rec, {"CLAUDE_PID": str(self.claude)}))
        self.assertFalse(writer_lock.same_process(writer_lock.read(self.root), {}))    # no CLAUDE_PID: never

    def test_session_start_after_clear_does_not_warn(self):
        writer_lock.acquire(self.root, "reel transcribe", self.env("A", self.claude)).release()
        payload = {"hook_event_name": "SessionStart", "source": "clear", "session_id": "B", "cwd": str(self.root)}
        _, out, _ = hook(CTX, payload, no_session_env())                    # no CLAUDE_PID: not provably ours
        self.assertIn("another session is working in this client", ctx_of(out))
        _, out, _ = hook(CTX, payload, no_session_env(CLAUDE_PID=str(self.claude)))
        self.assertNotIn("another session is working in this client", ctx_of(out))


class TestSourcesNeverOfferedForChange(HookFixture):
    """T3.7 review I2: the eval protect-client-sources showed plans offering `mv` inside data/Raw "once you confirm".
    The client-folder context and the editor output style both rule that out and point to a copy under output/."""

    def test_client_folder_context_forbids_offering_source_changes(self):
        ctx = self.start(self.root)
        self.assertIn("assets/ and data/ are read-only: never offer to rename, move, convert, overwrite or delete "
                      "anything inside them", ctx)
        self.assertIn("not even once the editor confirms", ctx)
        self.assertIn("offer a copy under output/", ctx)

    def test_editor_output_style_says_the_same(self):
        style = (SK / "output-styles/whynot-cut-editor.md").read_text(encoding="utf-8")
        self.assertIn("Never offer to rename, move, convert, overwrite or delete anything inside them, not even "
                      "\"once you confirm\"", style)
        self.assertIn("Offer a copy under `output/`", style)


if __name__ == "__main__":
    unittest.main()
