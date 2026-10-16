"""3.0 Phase 4 Task 20 (R-T8): tools/ci/security_watch.py and .github/workflows/security-watch.yml.

The watch opens an issue (assigned to the owner, so GitHub emails him) when a push comes from outside the allowlist,
a ref is force-pushed or deleted, or the repo goes public. The script is tested here on recorded-shape event payloads
(synthetic SHAs, fake outsiders at example.invalid); the workflow is checked as text: pinned official actions only,
Linux only, least-privilege permissions, and the `if:` prefilter (which cannot read the allowlist file) must carry the
same login and email as .github/security-allowlist.json.
Run:  bash tools/test.sh -p test_security_watch.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
SCRIPT = REPO / "tools" / "ci" / "security_watch.py"
WORKFLOW = REPO / ".github" / "workflows" / "security-watch.yml"
WORKFLOW_PATHS = REPO / ".github" / "workflows" / "security-watch-paths.yml"
ALLOWFILE = REPO / ".github" / "security-allowlist.json"
MACOS_WORKFLOW = REPO / ".github" / "workflows" / "macos.yml"


def _load():
    spec = importlib.util.spec_from_file_location("whynot_security_watch", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sw = _load()

ALLOW = {"pushers": ["thewhynotai"], "emails": ["info@thewhynot.ai"]}
BEFORE = "1111111111111111111111111111111111111111"
AFTER = "2222222222222222222222222222222222222222"
ZERO = "0" * 40


def person(email, name="Someone", username=None):
    d = {"name": name, "email": email}
    if username:
        d["username"] = username
    return d


def commit(author_email="info@thewhynot.ai", committer_email=None, sha="3333333333333333333333333333333333333333"):
    return {"id": sha, "message": "x", "author": person(author_email),
            "committer": person(committer_email or author_email)}


def push(pusher="thewhynotai", commits=None, **kw):
    cs = [commit()] if commits is None else commits
    p = {"ref": "refs/heads/release/3.0", "before": BEFORE, "after": AFTER, "created": False, "deleted": False,
         "forced": False, "pusher": {"name": pusher, "email": "info@thewhynot.ai"}, "sender": {"login": pusher},
         "commits": cs, "head_commit": cs[-1] if cs else None,
         "repository": {"full_name": "thewhynotai/whynot-cut", "private": True}}
    p.update(kw)
    return p


def run_main(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = sw.main(argv, env=env if env is not None else {})
    return rc, out.getvalue(), err.getvalue()


def parse_github_output(text):
    """The runner's rule: `name=value` lines, or `name<<DELIM` ... a line that equals DELIM (first one ends it)."""
    out, lines, i = {}, text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            continue
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            name, _, delim = line.partition("<<")
            body = []
            while i < len(lines) and lines[i] != delim:
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                raise AssertionError("unterminated heredoc " + delim)
            i += 1
            out[name] = "\n".join(body)
        else:
            name, _, val = line.partition("=")
            out[name] = val
    return out


class TestFindings(unittest.TestCase):
    def test_allowed_normal_push_has_no_finding(self):
        self.assertEqual(sw.findings("push", push(), ALLOW), [])

    def test_allowed_noreply_form_of_the_owner(self):
        c = commit("123456+thewhynotai@users.noreply.github.com")
        self.assertEqual(sw.findings("push", push(commits=[c]), ALLOW), [])

    def test_noreply_of_somebody_else_is_a_finding(self):
        c = commit("999+mallory@users.noreply.github.com")
        f = sw.findings("push", push(commits=[c]), ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("mallory", f[0])

    def test_noreply_does_not_match_by_the_id_alone_or_a_look_alike(self):
        for e in ("123456+thewhynotai-evil@users.noreply.github.com", "thewhynotai@evil.example.invalid",
                  "123456+thewhynotai@users.noreply.github.com.example.invalid"):
            self.assertTrue(sw.findings("push", push(commits=[commit(e)]), ALLOW), e)

    def test_outsider_pusher(self):
        f = sw.findings("push", push(pusher="mallory"), ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("mallory", f[0])
        self.assertIn("refs/heads/release/3.0", f[0])
        self.assertIn(BEFORE[:7], f[0])
        self.assertIn(AFTER[:7], f[0])
        self.assertNotIn(AFTER, f[0])       # short SHAs only

    def test_allowed_pusher_with_outsider_commit_author(self):
        f = sw.findings("push", push(commits=[commit("mallory@example.invalid")]), ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("mallory@example.invalid", f[0])
        self.assertIn("author", f[0])

    def test_outsider_committer_email(self):
        c = commit("info@thewhynot.ai", committer_email="mallory@example.invalid")
        f = sw.findings("push", push(commits=[c]), ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("committer", f[0])
        self.assertIn("mallory@example.invalid", f[0])

    def test_github_web_committer_is_not_a_finding_but_its_author_still_is(self):
        # A merge or web edit by the owner: author = owner, committer = GitHub's own noreply@github.com.
        ok = commit("info@thewhynot.ai", committer_email="noreply@github.com")
        self.assertEqual(sw.findings("push", push(commits=[ok]), ALLOW), [])
        bad = commit("mallory@example.invalid", committer_email="noreply@github.com")
        self.assertEqual(len(sw.findings("push", push(commits=[bad]), ALLOW)), 1)

    def test_head_commit_is_checked_even_when_commits_is_empty(self):
        p = push(commits=[])
        p["head_commit"] = commit("mallory@example.invalid")
        self.assertEqual(len(sw.findings("push", p, ALLOW)), 1)

    def test_the_same_outsider_email_is_reported_once(self):
        cs = [commit("mallory@example.invalid", sha="a" * 40), commit("mallory@example.invalid", sha="b" * 40)]
        f = sw.findings("push", push(commits=cs), ALLOW)
        self.assertEqual(sum("mallory@example.invalid" in x for x in f), 1)

    def test_forced_push_from_an_allowed_pusher_is_always_a_finding(self):
        f = sw.findings("push", push(forced=True), ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("force", f[0].lower())
        self.assertIn("refs/heads/release/3.0", f[0])

    def test_deleted_ref_is_always_a_finding(self):
        p = push(deleted=True, after=ZERO, commits=[], head_commit=None)
        p["ref"] = "refs/tags/v3.0.0-p4"
        f = sw.findings("push", p, ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("deleted", f[0].lower())
        self.assertIn("refs/tags/v3.0.0-p4", f[0])

    def test_delete_event_is_always_a_finding(self):
        p = {"ref": "release/old", "ref_type": "branch", "sender": {"login": "thewhynotai"}}
        f = sw.findings("delete", p, ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("release/old", f[0])
        self.assertIn("deleted", f[0].lower())

    def test_member_added_and_edited(self):
        p = {"action": "added", "member": {"login": "mallory"}, "changes": {},
             "repository": {"full_name": "thewhynotai/whynot-cut"}}
        p["member"]["permission"] = "admin"
        f = sw.findings("member", p, ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("mallory", f[0])
        self.assertIn("admin", f[0])
        e = sw.findings("member", {"action": "edited", "member": {"login": "mallory"},
                                    "changes": {"permission": {"from": "read", "to": "admin"}}}, ALLOW)
        self.assertEqual(len(e), 1)
        self.assertEqual(sw.findings("member", {"action": "removed", "member": {"login": "mallory"}}, ALLOW), [])

    def test_public(self):
        f = sw.findings("public", {"repository": {"full_name": "thewhynotai/whynot-cut", "private": False}}, ALLOW)
        self.assertEqual(len(f), 1)
        self.assertIn("PUBLIC", f[0])

    def test_unrelated_event(self):
        for ev in ("issues", "pull_request", "workflow_dispatch", "schedule"):
            self.assertEqual(sw.findings(ev, {"action": "opened"}, ALLOW), [], ev)

    def test_case_insensitive(self):
        allow = {"pushers": ["TheWhyNotAI"], "emails": ["Info@TheWhyNot.AI"]}
        p = push(pusher="THEWHYNOTAI", commits=[commit("INFO@thewhynot.ai", committer_email="info@THEWHYNOT.ai")])
        self.assertEqual(sw.findings("push", p, allow), [])
        c = commit("123+THEWHYNOTAI@Users.NoReply.GitHub.com")
        self.assertEqual(sw.findings("push", push(commits=[c]), ALLOW), [])

    def test_outsider_pusher_and_outsider_author_are_both_named(self):
        f = sw.findings("push", push(pusher="mallory", commits=[commit("mallory@example.invalid")]), ALLOW)
        self.assertEqual(len(f), 2)

    def test_missing_pusher_is_a_finding(self):
        p = push()
        del p["pusher"]
        del p["sender"]
        self.assertTrue(sw.findings("push", p, ALLOW))

    def test_findings_are_single_line_whatever_the_payload_holds(self):
        evil = "x\nEOF\ntitle=pwned"
        p = push(pusher=evil, ref=evil, commits=[commit(evil + "@example.invalid")])
        for f in sw.findings("push", p, ALLOW):
            self.assertNotIn("\n", f)
            self.assertNotIn("\r", f)


    # -- P1: a push that touches the watch or CI is always reported, even from the owner --------------------------

    def touching(self, **lists):
        c = commit()
        c.update({"added": [], "modified": [], "removed": []})
        c.update(lists)
        return push(commits=[c])

    def test_owner_push_touching_github_dir_is_a_finding(self):
        for key in ("added", "modified", "removed"):
            f = sw.findings("push", self.touching(**{key: [".github/security-allowlist.json"]}), ALLOW)
            self.assertEqual(len(f), 1, key)
            self.assertIn(".github/security-allowlist.json", f[0])

    def test_owner_push_touching_the_script_or_workflows_is_a_finding(self):
        for path in ("tools/ci/security_watch.py", ".github/workflows/security-watch.yml",
                     ".github/workflows/macos.yml", ".GitHub/workflows/x.yml"):
            self.assertEqual(len(sw.findings("push", self.touching(modified=[path]), ALLOW)), 1, path)

    def test_other_ci_and_ordinary_paths_are_not_a_finding(self):
        p = self.touching(modified=["tools/ci/smoke.sh", "whynot-cut/tests/test_x.py", "docs/ci.md",
                                    "tools/ci/security_watch.py.bak", "notes/.github/x"])
        self.assertEqual(sw.findings("push", p, ALLOW), [])

    def test_changed_list_from_the_api_is_checked_too(self):
        self.assertEqual(sw.findings("push", push(), ALLOW, changed=["docs/ci.md"]), [])
        f = sw.findings("push", push(), ALLOW, changed=["docs/ci.md", ".github/security-allowlist.json"])
        self.assertEqual(len(f), 1)
        self.assertIn(".github/security-allowlist.json", f[0])
        self.assertNotIn("docs/ci.md", f[0])

    def test_changed_list_unavailable_or_cut_at_300_cannot_be_verified(self):
        f = sw.findings("push", push(), ALLOW, changed=["!unavailable"])
        self.assertEqual(len(f), 1)
        self.assertIn("could not", f[0].lower())
        f = sw.findings("push", push(), ALLOW, changed=[f"src/f{i}.py" for i in range(300)])
        self.assertEqual(len(f), 1)
        self.assertIn("300", f[0])
        self.assertEqual(sw.findings("push", push(), ALLOW, changed=[f"src/f{i}.py" for i in range(299)]), [])

    def test_many_touched_paths_stay_one_bounded_line(self):
        f = sw.findings("push", push(), ALLOW, changed=[f".github/f{i}.yml" for i in range(40)])
        self.assertEqual(len(f), 1)
        self.assertLess(len(f[0]), 600)
        self.assertIn("more", f[0])

    def test_changed_list_is_ignored_for_other_events(self):
        self.assertEqual(sw.findings("public", {}, ALLOW, changed=[".github/x"]), ["The repository was made PUBLIC."])

    # -- P2-2: nothing from the payload may render as markdown, a link or an @-mention ------------------------------

    def strip_code_spans(self, line):
        return re.sub(r"`[^`]*`", "[span]", line)

    def test_attacker_text_only_ever_appears_inside_code_spans(self):
        evil = "[x](https://evil.invalid) @someone"
        p = push(pusher=evil, ref="refs/heads/" + evil, commits=[commit(evil + "@example.invalid")])
        p["commits"][0].update({"modified": [".github/" + evil]})
        lines = sw.findings("push", p, ALLOW)
        self.assertGreaterEqual(len(lines), 3)
        for line in lines:
            outside = self.strip_code_spans(line)
            for bad in ("[x]", "evil.invalid", "@someone", "https://"):
                self.assertNotIn(bad, outside, line)
            self.assertNotIn("`", outside, line)
        self.assertTrue(any("`" + evil + "@example.invalid`" in line for line in lines))

    def test_backticks_in_the_payload_cannot_close_a_code_span(self):
        evil = "a` @someone `b"
        for line in sw.findings("push", push(pusher=evil), ALLOW):
            self.assertNotIn("@someone", self.strip_code_spans(line))
            self.assertEqual(line.count("`") % 2, 0)
        self.assertNotIn("`", sw._clean(evil))

    def test_member_and_delete_fields_are_code_spans_too(self):
        evil = "[x](https://evil.invalid) @someone"
        for ev, p in (("member", {"action": "added", "member": {"login": evil, "permission": evil}}),
                      ("delete", {"ref": evil, "ref_type": "branch", "sender": {"login": evil}})):
            for line in sw.findings(ev, p, ALLOW):
                for bad in ("[x]", "evil.invalid", "@someone"):
                    self.assertNotIn(bad, self.strip_code_spans(line), line)

    def test_issue_body_has_no_live_markdown_from_the_payload(self):
        evil = "[x](https://evil.invalid) @someone"
        found = sw.findings("push", push(pusher=evil, ref="refs/heads/" + evil), ALLOW)
        title, body = sw.build_issue("push", push(pusher=evil, ref="refs/heads/" + evil), found, {})
        for line in body.splitlines():
            for bad in ("[x]", "evil.invalid", "@someone"):
                self.assertNotIn(bad, self.strip_code_spans(line), line)
        self.assertNotIn("`", title)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.allow = self.dir / "allow.json"
        self.allow.write_text(json.dumps(ALLOW), encoding="utf-8")
        self.out = self.dir / "github_output"

    def payload_file(self, payload, name="event.json"):
        f = self.dir / name
        f.write_text(json.dumps(payload), encoding="utf-8")
        return f

    def env(self, event, payload):
        return {"GITHUB_EVENT_NAME": event, "GITHUB_EVENT_PATH": str(self.payload_file(payload)),
                "GITHUB_OUTPUT": str(self.out), "GITHUB_REPOSITORY": "thewhynotai/whynot-cut",
                "GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "42"}

    def test_clean_push_exits_0_and_writes_nothing(self):
        rc, _, _ = run_main(["--allowlist", str(self.allow)], self.env("push", push()))
        self.assertEqual(rc, 0)
        self.assertFalse(self.out.exists() and self.out.read_text(encoding="utf-8").strip())

    def test_findings_exit_0_and_write_title_and_body_in_heredoc_form(self):
        rc, _, _ = run_main(["--allowlist", str(self.allow)],
                            self.env("push", push(pusher="mallory", forced=True)))
        self.assertEqual(rc, 0)
        raw = self.out.read_text(encoding="utf-8")
        self.assertRegex(raw, r"(?m)^title=Security watch: ")
        self.assertRegex(raw, r"(?m)^body<<\S+$")
        got = parse_github_output(raw)
        self.assertEqual(sorted(got), ["body", "title"])
        self.assertNotIn("\n", got["title"])
        self.assertIn("mallory", got["body"])
        self.assertIn("force", got["body"].lower())
        self.assertIn("https://github.com/thewhynotai/whynot-cut/actions/runs/42", got["body"])

    def test_dry_run_prints_and_writes_no_output_file(self):
        rc, out, _ = run_main(["--dry-run", "--allowlist", str(self.allow)],
                              self.env("push", push(pusher="mallory")))
        self.assertEqual(rc, 0)
        self.assertIn("mallory", out)
        self.assertFalse(self.out.exists())

    def test_cli_event_and_payload_flags(self):
        f = self.payload_file({"repository": {"full_name": "x/y"}}, "pub.json")
        rc, out, _ = run_main(["--event", "public", "--payload", str(f), "--allowlist", str(self.allow),
                               "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("PUBLIC", out)

    def test_dry_run_with_no_findings_says_so(self):
        rc, out, _ = run_main(["--dry-run", "--allowlist", str(self.allow)], self.env("push", push()))
        self.assertEqual(rc, 0)
        self.assertIn("no findings", out.lower())

    def test_changed_files_flag(self):
        listing = self.dir / "changed.txt"
        env = self.env("push", push())
        listing.write_text("docs/ci.md\n\n  tools/ci/smoke.sh  \n", encoding="utf-8")
        rc, out, _ = run_main(["--dry-run", "--allowlist", str(self.allow), "--changed-files", str(listing)], env)
        self.assertEqual((rc, "no findings" in out.lower()), (0, True))
        listing.write_text("docs/ci.md\n.github/security-allowlist.json\n", encoding="utf-8")
        rc, out, _ = run_main(["--dry-run", "--allowlist", str(self.allow), "--changed-files", str(listing)], env)
        self.assertEqual(rc, 0)
        self.assertIn(".github/security-allowlist.json", out)
        listing.write_text("!unavailable\n", encoding="utf-8")
        rc, out, _ = run_main(["--dry-run", "--allowlist", str(self.allow), "--changed-files", str(listing)], env)
        self.assertEqual(rc, 0)
        self.assertIn("could not", out.lower())
        rc, _, err = run_main(["--allowlist", str(self.allow), "--changed-files", str(self.dir / "nope.txt")], env)
        self.assertEqual(rc, 2)
        self.assertTrue(err.strip())

    def test_unreadable_payload_exits_2(self):
        bad = self.dir / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        env = {"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(bad), "GITHUB_OUTPUT": str(self.out)}
        rc, _, err = run_main(["--allowlist", str(self.allow)], env)
        self.assertEqual(rc, 2)
        self.assertTrue(err.strip())
        for env in ({"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(self.dir / "missing.json")},
                    {"GITHUB_EVENT_NAME": "push"}, {}):
            self.assertEqual(run_main(["--allowlist", str(self.allow)], env)[0], 2)
        arr = self.payload_file([1, 2], "arr.json")
        self.assertEqual(run_main(["--allowlist", str(self.allow)],
                                  {"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(arr)})[0], 2)

    def test_unreadable_or_malformed_allowlist_exits_2(self):
        env = self.env("push", push())
        self.assertEqual(run_main(["--allowlist", str(self.dir / "nope.json")], env)[0], 2)
        for body in ("{oops", json.dumps({"pushers": "thewhynotai", "emails": []}),
                     json.dumps({"pushers": [], "emails": []}), json.dumps({"emails": ["a@b.c"]}),
                     json.dumps(["x"])):
            self.allow.write_text(body, encoding="utf-8")
            self.assertEqual(run_main(["--allowlist", str(self.allow)], env)[0], 2, body)

    def test_the_shipped_allowlist_loads_and_is_not_empty(self):
        a = sw.load_allowlist(ALLOWFILE)
        self.assertEqual(a["pushers"], ["thewhynotai"])
        self.assertEqual(a["emails"], ["info@thewhynot.ai"])
        self.assertIn("_note", json.loads(ALLOWFILE.read_text(encoding="utf-8")))

    def test_hostile_payload_cannot_inject_output_keys(self):
        evil = "refs/heads/x\nEOF\nbody<<EOF\ntitle=pwned"
        rc, _, _ = run_main(["--allowlist", str(self.allow)],
                            self.env("push", push(pusher="mallory", ref=evil)))
        self.assertEqual(rc, 0)
        got = parse_github_output(self.out.read_text(encoding="utf-8"))
        self.assertEqual(sorted(got), ["body", "title"])
        self.assertNotIn("pwned", got["title"].replace("title=pwned", ""))
        self.assertNotIn("\n", got["title"])

    def test_title_is_bounded(self):
        rc, _, _ = run_main(["--allowlist", str(self.allow)],
                            self.env("push", push(pusher="m" * 5000, ref="refs/heads/" + "r" * 5000)))
        self.assertEqual(rc, 0)
        got = parse_github_output(self.out.read_text(encoding="utf-8"))
        self.assertLessEqual(len(got["title"]), 200)
        self.assertLessEqual(len(got["body"]), 30000)


class TestGithubOutputHeredoc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"

    def test_delimiter_is_random_and_never_one_of_the_bodys_lines(self):
        body = "line one\nEOF\nWATCH_EOF\nghadelimiter\nWATCH_AAAA\nlast"
        seq = iter(["AAAA", "BBBB"])      # the first draw collides with a body line; the writer must redraw
        sw.write_github_output(self.out, "t", body, token=lambda n: next(seq))
        raw = self.out.read_text(encoding="utf-8")
        self.assertIn("body<<WATCH_BBBB\n", raw)
        got = parse_github_output(raw)
        self.assertEqual(got["body"], body)
        self.assertEqual(got["title"], "t")

    def test_default_delimiters_differ_between_runs_and_are_long(self):
        seen = set()
        for _ in range(5):
            sw.write_github_output(self.out, "t", "b")
        for m in re.finditer(r"(?m)^body<<(\S+)$", self.out.read_text(encoding="utf-8")):
            seen.add(m.group(1))
        self.assertEqual(len(seen), 5)
        self.assertTrue(all(len(d) >= 24 and d not in ("EOF", "WATCH_EOF") for d in seen))

    def test_appends_to_an_existing_output_file(self):
        self.out.write_text("earlier=1\n", encoding="utf-8")
        sw.write_github_output(self.out, "t", "b")
        got = parse_github_output(self.out.read_text(encoding="utf-8"))
        self.assertEqual(got["earlier"], "1")
        self.assertEqual(got["body"], "b")


class _WorkflowChecks:
    """Checks both security-watch workflows share. Subclasses set PATH and NAME (not a TestCase itself)."""
    PATH = None
    NAME = None

    @classmethod
    def setUpClass(cls):
        cls.text = cls.PATH.read_text(encoding="utf-8")
        cls.code = "\n".join(ln for ln in cls.text.splitlines() if not ln.lstrip().startswith("#"))
        m = re.search(r"(?m)^on:\n((?:[ \t]+.*\n|\n)+)", cls.code + "\n")
        cls.on = m.group(1) if m else ""

    def test_every_uses_is_an_official_action_pinned_by_a_40_hex_sha(self):
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", self.code)
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"^actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}$", u)
        co = [u for u in uses if u.startswith("actions/checkout@")]
        macos = re.search(r"actions/checkout@([0-9a-f]{40})", MACOS_WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(co, ["actions/checkout@" + macos.group(1)])
        self.assertRegex(self.text, r"actions/checkout@[0-9a-f]{40} # v\d")

    def test_linux_only_with_a_timeout(self):
        runs = re.findall(r"(?m)^\s*runs-on:\s*(\S+)", self.code)
        self.assertEqual(runs, ["ubuntu-24.04"])
        self.assertRegex(self.code, r"(?m)^\s+timeout-minutes:\s*5\s*$")
        self.assertNotRegex(self.code, r"(?i)macos|windows")

    def test_permissions_are_exactly_contents_read_and_issues_write(self):
        m = re.search(r"(?m)^permissions:\n((?:[ \t]+\S.*\n)+)", self.code + "\n")
        self.assertIsNotNone(m)
        got = {k.strip(): v.strip() for k, v in (ln.split(":", 1) for ln in m.group(1).splitlines())}
        self.assertEqual(got, {"contents": "read", "issues": "write"})
        self.assertEqual(len(re.findall(r"(?m)^\s*permissions:", self.code)), 1)

    def test_name_and_no_secrets(self):
        self.assertRegex(self.text, rf"(?m)^name: {re.escape(self.NAME)}$")
        self.assertNotRegex(self.code, r"secrets\.")
        self.assertNotRegex(self.code, r"(?m)^\s*(pull_request_target|pull_request):")
        self.assertIn("persist-credentials: false", self.code)
        self.assertIn("sparse-checkout", self.code)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.code)
        self.assertIn("--assignee thewhynotai", self.code)
        self.assertIn("--label security", self.code)
        self.assertIn("gh label create security --force", self.code)
        self.assertIn("Security watch BROKE", self.code)
        self.assertNotRegex(self.code, r"setup-python")

    def test_untrusted_values_never_sit_inside_run_scripts(self):
        # Branch names, pusher names and commit text are attacker-controlled: `${{ ... }}` of them inside `run:`
        # would be shell injection. Only env: blocks may carry step outputs.
        blocks = re.findall(r"(?m)^[ \t]+run:[ \t]*[|>]-?\n((?:[ \t]{10,}[^\n]*\n)+)", self.code + "\n")
        self.assertGreaterEqual(len(blocks), 3)
        for block in blocks:
            self.assertNotRegex(block, r"\$\{\{\s*(github\.event|steps\.|github\.head_ref|github\.ref_name)")

    def _checkout_with(self):
        m = re.search(r"(?ms)uses:\s*actions/checkout@\S+[^\n]*\n\s+with:\n((?:[ \t]{10,}.*\n|\n)+)", self.code)
        self.assertIsNotNone(m)
        return m.group(1)

    def test_checkout_uses_the_trusted_ref_never_the_pushed_commit(self):
        # The pushed commit's own script and allowlist must never judge that push (an outsider could edit them).
        with_block = self._checkout_with()
        ref = re.search(r"(?m)^\s+ref:\s*(.+)$", with_block)
        self.assertIsNotNone(ref, "checkout has no ref:")
        expr = ref.group(1)
        self.assertNotRegex(expr, r"github\.sha|github\.ref\b|github\.event\.after|head_ref")
        self.assertIn("github.event.before", expr)
        self.assertIn("'" + "0" * 40 + "'", expr)
        self.assertIn("env.TRUSTED_BASE", expr)              # main holds no 3.0 files until release day
        self.assertRegex(self.text, r"(?m)^env:\n  TRUSTED_BASE: release/3\.0$")
        self.assertIn("persist-credentials: false", with_block)
        self.assertIn("sparse-checkout", with_block)

    def test_changed_files_come_from_the_api_and_reach_the_script(self):
        # No git fetch: persist-credentials is false, and the API also works for a force-pushed-away base.
        self.assertRegex(self.code, r"gh api[^\n]*compare/")
        self.assertIn("--changed-files", self.code)
        self.assertIn("!unavailable", self.code)

    def test_runs_the_one_script_entry_point(self):
        self.assertEqual(re.findall(r"python3 (tools/ci/\S+\.py)", self.code), ["tools/ci/security_watch.py"])
        self.assertTrue(SCRIPT.is_file())

    def test_header_is_honest_about_what_it_cannot_see(self):
        head = "\n".join(self.text.splitlines()[:60])
        self.assertRegex(head, r"(?i)minutes")
        self.assertNotRegex(head, r"(?i)scope")          # no claim that a token scope stops a workflow edit


class TestSecurityWatchWorkflow(_WorkflowChecks, unittest.TestCase):
    PATH = WORKFLOW
    NAME = "Security watch"

    def test_triggers_are_real_workflow_events_and_cover_every_watched_case(self):
        events = set(re.findall(r"(?m)^  ([a-z_]+):", self.on))
        # `member` is NOT a GitHub Actions trigger (an unknown event would invalidate the whole file), so it must
        # not be listed. `delete` is left out on purpose: a push with deleted:true already covers a deletion, and
        # listing both would open two issues for one deletion.
        self.assertEqual(events, {"push", "public", "workflow_dispatch"})
        self.assertNotRegex(self.on, r"paths(-ignore)?:")
        self.assertRegex(self.on, r"(?s)push:.*branches:\s*\[?\s*[\"']?\*\*")
        self.assertRegex(self.on, r"(?s)push:.*tags:\s*\[?\s*[\"']?\*\*")

    def test_prefilter_matches_the_allowlist_file_and_skips_only_the_boring_push(self):
        allow = json.loads(ALLOWFILE.read_text(encoding="utf-8"))
        m = re.search(r"(?ms)^    if:\s*>-?\n((?:[ \t]{6,}.*\n)+)", self.code)
        self.assertIsNotNone(m, "job-level if: not found")
        expr = m.group(1)
        # The `if:` cannot read files, so the allowlisted login and email live inline; they must equal the JSON file.
        self.assertEqual(sorted(set(re.findall(r"github\.event\.pusher\.name\s*!=\s*'([^']+)'", expr))),
                         sorted(allow["pushers"]))
        emails = set(re.findall(r"head_commit\.author\.email\s*!=\s*'([^']+)'", expr))
        self.assertEqual(sorted(emails), sorted(allow["emails"]))
        self.assertNotIn("committer", expr)
        self.assertIn("github.event.forced", expr)
        self.assertIn("github.event.deleted", expr)
        self.assertRegex(expr, r"github\.event_name\s*!=\s*'push'")      # everything but a push always runs
        self.assertIn("must match .github/security-allowlist.json", self.text)

    def test_header_states_the_honest_deploy_key_limit(self):
        head = "\n".join(self.text.splitlines()[:60])
        self.assertRegex(head, r"(?i)deploy key")
        self.assertRegex(head, r"(?i)not covered")
        self.assertRegex(head, r"(?i)three tags")
        self.assertRegex(head, r"(?i)default branch")
        self.assertIn("security-watch-paths.yml", head)


class TestSecurityWatchPathsWorkflow(_WorkflowChecks, unittest.TestCase):
    PATH = WORKFLOW_PATHS
    NAME = "Security watch (paths)"

    def test_triggers_are_a_push_filtered_to_the_watch_and_ci_files_only(self):
        self.assertEqual(set(re.findall(r"(?m)^  ([a-z_]+):", self.on)), {"push"})
        m = re.search(r"(?m)^    paths:\s*\[(.*)\]\s*$", self.on)
        self.assertIsNotNone(m, "paths: must be a one-line list")
        self.assertEqual(re.findall(r"[\"']([^\"']+)[\"']", m.group(1)), [".github/**", "tools/ci/security_watch.py"])
        self.assertNotRegex(self.on, r"branches|tags|paths-ignore")      # no branch filter: every branch is watched
        self.assertRegex(self.text, r"(?i)ignores? path filters on tag pushes")

    def test_has_no_prefilter_so_the_touched_paths_are_always_reported(self):
        self.assertNotRegex(self.code, r"(?m)^    if:")

    def test_header_points_at_the_main_workflow(self):
        head = "\n".join(self.text.splitlines()[:40])
        self.assertIn("security-watch.yml", head)
        self.assertRegex(head, r"(?i)tag push")


class TestTwoWorkflowsAgree(unittest.TestCase):
    """Short and similar by design: the trusted checkout, the changed-files step and the entry point must not drift."""
    def setUp(self):
        self.a = WORKFLOW.read_text(encoding="utf-8")
        self.b = WORKFLOW_PATHS.read_text(encoding="utf-8")

    @staticmethod
    def step(text, name):
        m = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", text)
        assert m, name
        return chr(10).join(ln for ln in m.group(1).splitlines() if not ln.lstrip().startswith("#"))

    def test_same_checkout_ref_changed_files_step_and_failure_step(self):
        ref = r"(?m)^\s+ref: (.+)$"
        self.assertEqual(re.search(ref, self.a).group(1), re.search(ref, self.b).group(1))
        for name in ("List the files this push changed", "Check the event", "Open the issue",
                     "Say the watch itself broke"):
            self.assertEqual(self.step(self.a, name), self.step(self.b, name), name)

    def test_same_pin_and_permissions(self):
        pin = r"actions/checkout@[0-9a-f]{40} # v[\d.]+"
        self.assertEqual(re.search(pin, self.a).group(0), re.search(pin, self.b).group(0))
        perms = r"(?m)^permissions:\n(?:  .*\n)+"
        self.assertEqual(re.search(perms, self.a).group(0), re.search(perms, self.b).group(0))


class TestDocs(unittest.TestCase):
    def test_ci_md_has_a_security_watch_section(self):
        t = (REPO / "docs" / "ci.md").read_text(encoding="utf-8")
        self.assertIn("## Security watch", t)
        sec = t.split("## Security watch", 1)[1]
        for needle in ("security-watch.yml", "security-watch-paths.yml", "Billing", "added/modified/removed", "Deploy keys", "minutes", "issue", "three tags", "default branch",
                       "Security log", "Personal access tokens", "SSH and GPG keys", "Collaborators"):
            self.assertIn(needle, sec)
        self.assertNotRegex(sec, r"(?i)workflow.{0,8}scope")
        for n in range(1, 6):
            self.assertRegex(sec, rf"(?m)^{n}\. ")


if __name__ == "__main__":
    unittest.main()
