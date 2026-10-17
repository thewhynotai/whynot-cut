#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""One entry point for the free security scanners (Addendum L §L3; Phase 4 Task 39 / L-T1). Stdlib only.

  python tools/security/scan.py --all                 SAST + secrets + deps + SBOM + lock hashes, one summary
  python tools/security/scan.py --sast|--secrets|--deps|--sbom|--locks
  options: --root DIR (tree to scan, default the repo) --gate NAME (report name) --history (secrets: full git history)
           --offline (do not touch the network) --no-registry (Semgrep: our rules only) --baseline FILE
           --out DIR (summary folder, default docs/security) --raw DIR (raw JSON, default dist/) --no-report

Exit codes: 0 clean | 1 a NEW High/Critical finding (not in the baseline) | 2 usage or baseline file problem
            3 degraded (a database or rule pack was NOT checked, or coverage was partial) | 4 a scanner is missing, the
            wrong version, altered after install, or failed. Never a silent pass: every scanner is listed with its status.
A degraded scanner can be accepted ONLY by a `known_gaps` entry in the baseline (reason, owner task, review date); the
report then says "accepted gap" and the exit code ignores it. Nothing else turns a degraded run into a pass.

Network: only the vulnerability databases (OSV, PyPI advisories, npm audit) and the Semgrep registry rule packs.
Metrics and version checks are switched off for every tool that has a switch. Nothing of ours is uploaded.
A secret value is never printed, logged or written: gitleaks runs with --redact, the value fields are dropped, and the
raw JSON of every tool is scrubbed of source text (Bandit `code`, Semgrep `lines` and `metavars`) before it is kept.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from fsutil import walk_files, which_safe  # noqa: E402
from install_tools import safe_env  # noqa: E402

SEV_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
BLOCKING = ("CRITICAL", "HIGH")
REGISTRY_PACKS = ("p/python", "p/javascript", "p/typescript", "p/secrets")
BANDIT_DIRS = ("whynot-cut/engine", "whynot-cut/hooks", "whynot-cut/installer/core", "tools")
BANDIT_SKIP = "B404,B603"  # subprocess import / list-form call: our calls are list-form by rule (spec L3)
SEMGREP_EXCLUDES = ("node_modules", "dist", ".git", "*.min.js", "__pycache__", ".venv", "venv",
                    "adobe/**/build", "adobe/panel-ui/dev/out")  # build output and bundles double-count their sources
EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_DEGRADED, EXIT_TOOL = 0, 1, 2, 3, 4
OSV_HOST = ("api.osv.dev", 443)
NPM_INTEGRITY = ("sha512-", "sha384-", "sha256-")


class ScanError(Exception):
    pass


class BaselineError(ScanError):
    pass


# ---------------------------------------------------------------------------------------------------------- config

def versions():
    return json.loads((HERE / "versions.json").read_text(encoding="utf-8"))


def platform_key():
    return "win-x64" if os.name == "nt" else "linux-x64"


def tools_home():
    env = os.environ.get("WNC_SEC_TOOLS")
    return Path(env) if env else Path(versions()["tools_home_default"])


def tool_exe(name):
    home = tools_home()
    if name in ("semgrep", "bandit", "pip-audit"):
        sub = "Scripts" if os.name == "nt" else "bin"
        return home / "venv" / sub / (name + (".exe" if os.name == "nt" else ""))
    return home / "bin" / versions()["binaries"][name]["platforms"][platform_key()]["exe"]


def pinned_version(name):
    v = versions()
    if name in v["binaries"]:
        return v["binaries"][name]["version"]
    return v["python_tools"]["packages"][name]["version"]


def clean_env():
    """The environment every scanner runs in: metrics and update checks off, caches inside the tools home (per user, on
    D:), and nothing that could point a scanner at a cloud account (every SEMGREP_* variable of the caller is dropped)."""
    env = {k: v for k, v in safe_env().items() if not k.upper().startswith("SEMGREP_")}
    cache = tools_home() / "cache"
    env.update(SEMGREP_SEND_METRICS="off", SEMGREP_ENABLE_VERSION_CHECK="0", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CACHE_DIR=str(cache / "pip"), XDG_CACHE_HOME=str(cache),
               SEMGREP_SETTINGS_FILE=str(cache / "semgrep" / "settings.yml"),
               SEMGREP_VERSION_CACHE_PATH=str(cache / "semgrep" / "version-cache"),
               DO_NOT_TRACK="1", NO_COLOR="1", NPM_CONFIG_UPDATE_NOTIFIER="false")
    return env


def _need_abs(argv):
    if not (isinstance(argv, list) and argv and os.path.isabs(str(argv[0]))):
        raise ValueError("a scanner command must be a list with an absolute program path (planted-binary class): %r" % (argv[:1],))


def run(argv, cwd=None, timeout=1800, input_bytes=None):
    """List-form, no shell, absolute executable. Returns (rc, stdout, stderr)."""
    _need_abs(argv)
    p = subprocess.run(argv, cwd=cwd, env=clean_env(), capture_output=True, timeout=timeout, input=input_bytes)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def run_bytes(argv, cwd=None, input_bytes=None, timeout=1800):
    """Like run() but stdout comes back as raw bytes (git cat-file --batch)."""
    _need_abs(argv)
    p = subprocess.run(argv, cwd=cwd, env=clean_env(), capture_output=True, timeout=timeout, input=input_bytes)
    return p.returncode, p.stdout


# ---------------------------------------------------------------------------------------------------- tool states

VERSION_ARGS = {"semgrep": ["--version"], "bandit": ["--version"], "pip-audit": ["--version"],
                "gitleaks": ["version"], "osv-scanner": ["--version"]}
VERSION_RE = {"semgrep": r"^\s*(\d+\.\d+\.\d+)\s*$", "bandit": r"bandit\s+(\d+\.\d+\.\d+)",
              "pip-audit": r"pip-audit\s+(\d+\.\d+\.\d+)", "gitleaks": r"^\s*(\d+\.\d+\.\d+)\s*$",
              "osv-scanner": r"osv-scanner version:\s*(\d+\.\d+\.\d+)"}
_STATE_CACHE = {}


def integrity_problem(name):
    """None when the installed tool is byte-identical to what install_tools.py put there, else a one-line reason. Checked
    BEFORE the tool is run (a replaced binary would run with our permissions, even for `--version`)."""
    import install_tools as it
    home = tools_home()
    if name in versions()["binaries"]:
        return it.verify_installed(name, home)
    return it.verify_python_tool(name, home, everything=True)


def tool_state(name):
    """('ok'|'missing'|'mismatch'|'altered', found_version_or_None, message). Never raises."""
    key = (name, str(tools_home()))
    if key in _STATE_CACHE:
        return _STATE_CACHE[key]
    _STATE_CACHE[key] = out = _tool_state(name)
    return out


def _tool_state(name):
    exe = tool_exe(name)
    pin = pinned_version(name)
    if not exe.exists():
        return ("missing", None, "MISSING %s (expected at %s); run: python tools/security/install_tools.py" % (name, exe))
    try:
        bad = integrity_problem(name)
    except Exception as e:  # noqa: BLE001  a tampered manifest/RECORD must read as ALTERED, never as a traceback
        bad = "%s: integrity check failed (%s: %s)" % (name, type(e).__name__, e)
    if bad:
        return ("altered", None, "ALTERED %s: %s; run: python tools/security/install_tools.py" % (name, bad))
    try:
        rc, out, err = run([str(exe)] + VERSION_ARGS[name], timeout=120)
    except Exception as e:  # noqa: BLE001
        return ("missing", None, "MISSING %s: %s cannot be started (%s)" % (name, exe, e))
    m = re.search(VERSION_RE[name], out + "\n" + err, re.M)
    found = m.group(1) if m else None
    if found != pin:
        return ("mismatch", found, "VERSION MISMATCH %s: pinned %s, found %s; run: python tools/security/install_tools.py"
                % (name, pin, found))
    return ("ok", found, "")


# ------------------------------------------------------------------------------------------------------- findings

def fingerprint(tool, rule, file, key):
    """Stable across line moves: tool|rule|file|key (key = normalised code text + occurrence, or an advisory id)."""
    return hashlib.sha256(("%s|%s|%s|%s" % (tool, rule, file, key)).encode("utf-8")).hexdigest()[:20]


def norm_code(s):
    return re.sub(r"\s+", " ", s or "").strip()


def rel(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return str(path).replace("\\", "/")


def finding(tool, rule, severity, file, line, message, key):
    sev = severity.upper()
    sev = sev if sev in SEV_ORDER else "HIGH"
    return {"tool": tool, "rule": rule, "severity": sev, "file": file, "line": line,
            "message": message.strip().splitlines()[0][:300] if message else "",
            "fingerprint": fingerprint(tool, rule, file, key)}


def cvss_to_sev(score):
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "HIGH"  # unrated: treated as High until someone triages it
    return "CRITICAL" if s >= 9 else "HIGH" if s >= 7 else "MEDIUM" if s >= 4 else "LOW"


def number_occurrences(findings):
    """Two identical flagged lines in one file get different fingerprints (key#1, key#2): accepting one in the baseline
    never accepts a later copy of the same line. Order is the scanner's own order, stable for an unchanged file."""
    seen = {}
    out = []
    for f, key in findings:
        k = (f["tool"], f["rule"], f["file"], key)
        seen[k] = seen.get(k, 0) + 1
        f["fingerprint"] = fingerprint(f["tool"], f["rule"], f["file"], "%s#%d" % (key, seen[k]))
        out.append(f)
    return out


# ----------------------------------------------------------------------------------------------------- baseline

BASELINE_FIELDS = ("fingerprint", "tool", "rule", "file", "reason", "owner_task", "review_date")
GAP_FIELDS = ("tool", "code", "reason", "owner_task", "review_date")
# The reason codes a DEGRADED result can carry (a known gap accepts exactly one (tool, code) pair, never a whole tool).
GAP_CODES = ("offline", "registry-skipped", "scan-errors", "skipped-files", "skipped-requirements", "plugins-missing", "parse-errors")


def _check_entry(e, fields, where):
    for f in fields:
        v = e.get(f, "")
        if not isinstance(v, str) or not v.strip():
            raise BaselineError("%s (%s) has no text in %s: every accepted item needs a reason, an owner task and a review date"
                                % (where, e.get("rule", e.get("tool", "?")), f))
    try:
        datetime.date.fromisoformat(e["review_date"])
    except ValueError:
        raise BaselineError("%s: review_date %r is not YYYY-MM-DD" % (where, e["review_date"]))


def load_baseline_full(path):
    """-> (accepted {fingerprint: entry}, known_gaps {tool: entry}). A missing file is an empty baseline; a file that is
    not a JSON object, or an entry without reason/owner/date, is a BaselineError (exit 2)."""
    p = Path(path)
    if not p.exists():
        return {}, {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise BaselineError("baseline %s is not valid JSON: %s" % (p, e))
    if not isinstance(data, dict):
        raise BaselineError("baseline %s must be a JSON object with an `accepted` list" % p)
    out, gaps = {}, {}
    for key in ("accepted", "known_gaps"):
        if not isinstance(data.get(key, []), list):
            raise BaselineError("baseline %s: `%s` must be a list" % (p, key))
    for i, e in enumerate(data.get("accepted", [])):
        if not isinstance(e, dict):
            raise BaselineError("baseline entry #%d is not an object" % i)
        if e.get("tool") == "gitleaks":
            raise BaselineError("baseline entry #%d: a secret finding can never be baselined (L-G30). A real one is "
                                "rotated by the owner and handed over without its value; a fake one gets an exact allow "
                                "rule in .gitleaks.toml" % i)
        _check_entry(e, BASELINE_FIELDS, "baseline entry #%d" % i)
        out[e["fingerprint"]] = e
    for i, e in enumerate(data.get("known_gaps", [])):
        if not isinstance(e, dict):
            raise BaselineError("known_gaps entry #%d is not an object" % i)
        _check_entry(e, GAP_FIELDS, "known_gaps entry #%d" % i)
        if e["code"] not in GAP_CODES:
            raise BaselineError("known_gaps entry #%d: code %r is not one of %s" % (i, e["code"], ", ".join(GAP_CODES)))
        gaps[(e["tool"], e["code"])] = e
    return out, gaps


def load_baseline(path):
    return load_baseline_full(path)[0]


def split_by_baseline(findings, baseline, today=None):
    """-> (new, accepted, expired_entries). Nothing is hidden: accepted findings are counted and listed in the report."""
    today = today or datetime.date.today()
    new, accepted, expired = [], [], []
    for f in findings:
        e = baseline.get(f["fingerprint"])
        if e and f["tool"] != "gitleaks":
            accepted.append(f)
            if datetime.date.fromisoformat(e["review_date"]) < today and e not in expired:
                expired.append(e)
        else:
            new.append(f)
    return new, accepted, expired


def apply_known_gaps(results, gaps):
    """A DEGRADED scanner is marked accepted (shown, not hidden) only when EVERY reason code it carries has a
    `known_gaps` entry for (this tool, that code). A gap written for "offline" never accepts "scan errors"."""
    for r in results:
        if r["status"] != "DEGRADED":
            continue
        codes = r.get("codes") or []
        found = [gaps.get((r["tool"], c)) for c in codes]
        if codes and all(found):
            r["accepted_gap"] = {"reason": "; ".join(g["reason"] for g in found), "owner_task": found[0]["owner_task"],
                                 "review_date": min(g["review_date"] for g in found)}
    return results


# --------------------------------------------------------------------------------------------------------- network

def is_offline(explicit=False):
    if explicit or os.environ.get("WNC_SCAN_OFFLINE") == "1":
        return True
    try:
        socket.create_connection(OSV_HOST, timeout=4).close()
        return False
    except OSError:
        return True


# --------------------------------------------------------------------------------------------------------- results

def result(tool, status, findings=None, note="", version=None, codes=None):
    return {"tool": tool, "status": status, "findings": findings or [], "note": note, "version": version, "codes": list(codes or [])}


def need(name):
    """None when the tool is usable, else a MISSING / MISMATCH / ALTERED result."""
    st, ver, msg = tool_state(name)
    if st == "ok":
        return None
    return result(name, {"missing": "MISSING", "mismatch": "MISMATCH", "altered": "ALTERED"}[st], note=msg, version=ver)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------------------------------------------------ SAST

def semgrep_argv(root, rules_dir, out_json, registry=True):
    argv = [str(tool_exe("semgrep")), "scan", "--metrics=off", "--disable-version-check", "--quiet", "--json",
            "--output", str(out_json), "--no-git-ignore", "--config", str(rules_dir)]
    if registry:
        for pack in REGISTRY_PACKS:
            argv += ["--config", pack]
    for ex in SEMGREP_EXCLUDES:
        argv += ["--exclude", ex]
    argv.append(str(root))
    return argv


def semgrep_sev(r):
    meta = (r.get("extra") or {}).get("metadata") or {}
    if meta.get("wnc_severity"):
        return meta["wnc_severity"]
    return {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}.get((r.get("extra") or {}).get("severity"), "MEDIUM")


def source_text(root, rel_path, start, end):
    """The flagged source lines, read from the file (Semgrep CE does not return them without a login)."""
    try:
        lines = (Path(root) / rel_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return norm_code(" ".join(lines[max(start - 1, 0):max(end, start)]))


def parse_semgrep(data, root):
    keyed = []
    for r in data.get("results", []):
        rule = r["check_id"]
        if "wnc-" in rule:  # our rule ids come prefixed with the rules folder path
            rule = rule[rule.index("wnc-"):]
        f = rel(r["path"], root)
        text = source_text(root, f, r["start"]["line"], r["end"]["line"]) or "line %s" % r["start"]["line"]
        msg = (r.get("extra") or {}).get("message", "") if "wnc-" in r["check_id"] else "registry rule (message withheld: it may quote the matched value)"
        keyed.append((finding("semgrep", rule, semgrep_sev(r), f, r["start"]["line"], msg, text), text))
    return number_occurrences(keyed)


def scrub_semgrep(data):
    """Raw JSON kept on disk without source text or matched values. Our own rules have fixed messages; a registry rule's
    message may interpolate the matched value, so it is dropped (the rule id says what it is)."""
    for r in data.get("results", []):
        ex = r.get("extra") or {}
        for k in ("lines", "metavars", "fingerprint", "dataflow_trace", "fix", "fix_regex", "validation_state", "engine_kind"):
            ex.pop(k, None)
        if "wnc-" not in r.get("check_id", ""):
            ex.pop("message", None)
    for e in data.get("errors", []):
        for k in ("spans", "long_msg", "message"):
            e.pop(k, None)
    return data


SEMGREP_COVERAGE_LOSS = ("size", "timeout", "too_big", "error", "unable", "binary")


def scan_semgrep(root, raw_dir, offline, registry=True):
    miss = need("semgrep")
    if miss:
        return miss
    rules = REPO / ".semgrep"
    out_json = Path(raw_dir) / "semgrep.json"
    use_registry = registry and not offline
    argv = semgrep_argv(root, rules, out_json, registry=use_registry)
    if out_json.exists():
        out_json.unlink()  # never read a stale file of an earlier run
    rc, so, se = run(argv, cwd=str(root))
    if rc not in (0, 1) or not out_json.exists():
        return result("semgrep", "FAILED", note="semgrep exit %s: %s" % (rc, (se or so).strip()[-400:]), version=pinned_version("semgrep"))
    data = scrub_semgrep(json.loads(out_json.read_text(encoding="utf-8")))  # scrub FIRST: nothing unscrubbed stays on disk if parsing fails
    write_json(out_json, data)
    findings = parse_semgrep(data, root)
    scanned = (data.get("paths") or {}).get("scanned") or []
    skipped = (data.get("paths") or {}).get("skipped") or []
    def etype(e):
        t = e.get("type")
        return t[0] if isinstance(t, list) and t else t
    # a file Semgrep could not parse at all (Syntax/Lexical error) or any error-level problem had NO rules applied;
    # PartialParsing (most of the file read) is only counted in the note
    fatal = [e for e in data.get("errors", []) if e.get("level") == "error" or etype(e) in ("Syntax error", "Lexical error")]
    partial = [e for e in data.get("errors", []) if etype(e) == "PartialParsing"]
    lost = [s for s in skipped if isinstance(s, dict) and any(w in str(s.get("reason", "")).lower() for w in SEMGREP_COVERAGE_LOSS)]
    notes, status, codes = [], "OK", []
    if not scanned and not findings:
        return result("semgrep", "FAILED", note="semgrep scanned 0 files under %s (wrong path?)" % root, version=pinned_version("semgrep"))
    if not use_registry:
        status = "DEGRADED"
        codes.append("offline" if offline else "registry-skipped")
        notes.append("registry packs (%s) NOT run (%s); only our .semgrep rules" % (", ".join(REGISTRY_PACKS), "offline" if offline else "--no-registry"))
    if fatal:
        status = "DEGRADED"
        codes.append("scan-errors")
        notes.append("%d scan error(s)" % len(fatal))
    if lost:
        status = "DEGRADED"
        codes.append("skipped-files")
        notes.append("%d file(s) skipped for size/timeout/other loss of coverage" % len(lost))
    if partial:
        notes.append("%d file(s) only partly parsed" % len(partial))
    notes.append("%d files scanned" % len(scanned))
    return result("semgrep", status, findings, "; ".join(notes), pinned_version("semgrep"), codes)


def bandit_argv(dirs, out_json):
    return [str(tool_exe("bandit")), "-r"] + [str(d) for d in dirs] + ["-f", "json", "-o", str(out_json), "-q",
                                                                      "--skip", BANDIT_SKIP]


PASSWORD_TESTS = ("B105", "B106", "B107")   # hard-coded password string / argument / default: the text quotes the value


def clean_bandit_text(r):
    txt = r.get("issue_text", "")
    if r.get("test_id") in PASSWORD_TESTS and ": " in txt:
        txt = txt.split(": ", 1)[0] + ": <redacted>"  # everything after the colon quotes the value, whatever quotes it holds
    return txt


def parse_bandit(data, root):
    keyed = []
    for r in data.get("results", []):
        f = rel(r["filename"], root)
        # the flagged line read from the file (bandit's own `code` field carries numbered context lines, which would
        # change the fingerprint whenever the file shifts)
        text = source_text(root, f, r["line_number"], r["line_number"]) or r["test_id"]
        keyed.append((finding("bandit", r["test_id"], r["issue_severity"], f, r["line_number"],
                             "%s: %s" % (r["test_name"], clean_bandit_text(r)), text), text))
    return number_occurrences(keyed)


NOSEC = re.compile(r"#\s*nosec\b(?P<rest>[^\r\n]*)")
NOSEC_CODES = re.compile(r"^\s*:?\s*(?:B\d{3}(?:\s*,\s*B\d{3})*)?")


def check_nosec(root, dirs):
    """Spec L3: every `# nosec` has a reason (at least a few words after the optional test ids)."""
    keyed = []
    for d in dirs:
        for p in walk_files(d):
            if not p.endswith(".py"):
                continue
            try:
                lines = Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for n, ln in enumerate(lines, 1):
                m = NOSEC.search(ln)
                if not m:
                    continue
                reason = NOSEC_CODES.sub("", m.group("rest"), count=1).strip(" -:\t")
                if len(reason) < 8:
                    text = norm_code(ln)
                    keyed.append((finding("bandit", "nosec-no-reason", "MEDIUM", rel(p, root), n,
                                          "`# nosec` without a written reason", text), text))
    return number_occurrences(keyed)


def scan_bandit(root, raw_dir):
    miss = need("bandit")
    if miss:
        return miss
    root = Path(root)
    real_layout = (root / "whynot-cut" / "engine").is_dir()
    if real_layout:
        absent = [d for d in BANDIT_DIRS if not (root / d).is_dir()]
        if absent:
            return result("bandit", "FAILED", note="configured scan folder(s) not found: %s (a path that moved would otherwise "
                          "scan nothing and pass)" % ", ".join(absent), version=pinned_version("bandit"))
        dirs = [root / d for d in BANDIT_DIRS]
    else:
        dirs = [root]  # a scratch tree (tests): scan it all
    out_json = Path(raw_dir) / "bandit.json"
    if out_json.exists():
        out_json.unlink()
    rc, so, se = run(bandit_argv(dirs, out_json), cwd=str(root))
    if rc not in (0, 1) or not out_json.exists():
        return result("bandit", "FAILED", note="bandit exit %s: %s" % (rc, (se or so).strip()[-400:]), version=pinned_version("bandit"))
    data = json.loads(out_json.read_text(encoding="utf-8"))
    findings = parse_bandit(data, root) + check_nosec(root, dirs)
    for r in data.get("results", []):
        r["issue_text"] = clean_bandit_text(r)
        r.pop("code", None)  # the source line may hold a hard-coded password (B105/B106): never kept on disk
        r.pop("line_range", None)
    write_json(out_json, data)
    notes, status = ["skipped %s (list-form subprocess, by rule)" % BANDIT_SKIP], "OK"
    codes = []
    if data.get("errors"):
        status = "DEGRADED"
        codes.append("parse-errors")
        notes.append("%d file(s) bandit could not parse" % len(data["errors"]))
    metrics = (data.get("metrics") or {}).get("_totals") or {}
    if not metrics.get("loc"):
        return result("bandit", "FAILED", note="bandit scanned 0 lines of code under %s" % ", ".join(str(d) for d in dirs), version=pinned_version("bandit"))
    notes.append("%d lines of code" % metrics["loc"])
    return result("bandit", status, findings, "; ".join(notes), pinned_version("bandit"), codes)


ESLINT_HIGH = ("no-unsanitized/", "security/detect-eval-with-expression", "security/detect-child-process",
               "security/detect-non-literal-require", "security/detect-unsafe-regex", "security/detect-buffer-noassert",
               "security/detect-new-buffer", "security/detect-disable-mustache-escape", "security/detect-pseudoRandomBytes")


def eslint_sev(rule):
    if rule and rule.startswith(ESLINT_HIGH):
        return "HIGH"
    if rule == "security/detect-object-injection":
        return "LOW"  # bracket access with a variable key: noisy, only a prototype-pollution risk; reviewed in the report
    return "MEDIUM"


def parse_eslint(items, root):
    keyed = []
    for f in items:
        for m in f.get("messages", []):
            if not m.get("ruleId"):
                continue  # a parse error: not a finding
            fp = rel(f["filePath"], root)
            text = norm_code(m.get("source", "")) or source_text(root, fp, m.get("line", 1), m.get("endLine") or m.get("line", 1))
            keyed.append((finding("eslint", m["ruleId"], eslint_sev(m["ruleId"]), fp, m.get("line", 0), m.get("message", ""), text), text))
    return number_occurrences(keyed)


def scan_eslint(root, raw_dir):
    """ESLint + eslint-plugin-security + eslint-plugin-no-unsanitized over the plain-JS surfaces of adobe/. The
    devDependencies come from the Adobe track (patch in lane3/hooks/L-T1); until they are installed this is DEGRADED
    (exit 3) unless the baseline lists it under `known_gaps`."""
    adobe = Path(root) / "adobe"
    cfg = adobe / "eslint.security.config.mjs"
    entry = adobe / "node_modules" / "eslint" / "bin" / "eslint.js"
    if not adobe.is_dir():
        return result("eslint", "OK", note="no adobe/ folder")
    if not (cfg.exists() and entry.exists()):
        return result("eslint", "DEGRADED", note="eslint security plugins NOT run: not installed in adobe/ (pending the Adobe "
                      "track's devDependencies patch, then `npm ci`); panel TS is covered by Semgrep wnc-raw-innerhtml",
                      codes=["plugins-missing"])
    node = which_safe("node")
    if not node:
        return result("eslint", "MISSING", note="MISSING node (not found on PATH)")
    rc, so, se = run([node, str(entry), "-c", str(cfg), "-f", "json"], cwd=str(adobe))
    try:
        items = json.loads(so)
    except ValueError:
        return result("eslint", "FAILED", note="eslint exit %s gave no JSON: %s" % (rc, se.strip()[-200:]))
    findings = parse_eslint(items, root)
    unparsed = sum(1 for f in items for m in f.get("messages", []) if m.get("fatal") or (m.get("ruleId") is None and m.get("severity") == 2))
    for f in items:
        for m in f.get("messages", []):
            m.pop("source", None)
    write_json(Path(raw_dir) / "eslint.json", items)
    if not items:
        return result("eslint", "FAILED", note="eslint linted 0 files (the config matched nothing: wrong path or glob?)")
    if unparsed:
        return result("eslint", "DEGRADED", findings, "%d file(s) eslint could not parse (NOT audited), %d files linted" % (unparsed, len(items)),
                      codes=["parse-errors"])
    return result("eslint", "OK", findings, "plain-JS surfaces of adobe/ (%d files)" % len(items))


# --------------------------------------------------------------------------------------------------------- secrets

def gitleaks_argv(root, out_json, history=False, config=None):
    # run with cwd=root and the path "." so reported paths are repo-relative (the allow rules in .gitleaks.toml match them)
    argv = [str(tool_exe("gitleaks")), "git" if history else "dir", ".", "--report-format", "json",
            "--report-path", str(out_json), "--redact", "--no-banner", "--exit-code", "0", "--log-level", "warn"]
    if not history:
        argv += ["--max-archive-depth", "2"]  # a key inside a zip/tar in the working tree
    if config:
        argv += ["--config", str(config)]
    return argv


GITLEAKS_RAW_KEEP = ("File", "StartLine", "EndLine", "RuleID", "Commit", "Fingerprint", "Description", "Tags", "Entropy")


def parse_gitleaks(items, root):
    """Value fields are dropped here: only file, line, rule and commit survive (HL5: Yunus rotates, we never print)."""
    out = []
    for it in items or []:
        f = rel(it.get("File", ""), root)
        key = "%s:%s:%s" % (it.get("Commit", "") or "tree", it.get("RuleID", "?"), it.get("StartLine", 0))
        x = finding("gitleaks", it.get("RuleID", "?"), "HIGH", f, it.get("StartLine", 0),
                    "secret-like value (redacted) rule %s" % it.get("RuleID", "?"), key)
        if it.get("Commit"):
            x["commit"] = it["Commit"][:12]
        out.append(x)
    return out


def scan_gitleaks(root, raw_dir, history=False):
    miss = need("gitleaks")
    if miss:
        return miss
    root = Path(root)
    out_json = Path(raw_dir) / ("gitleaks-history.json" if history else "gitleaks-tree.json")
    cfg = root / ".gitleaks.toml"
    if not cfg.exists():
        cfg = REPO / ".gitleaks.toml"
    argv = gitleaks_argv(root, out_json, history, cfg if cfg.exists() else None)
    if out_json.exists():
        out_json.unlink()
    rc, so, se = run(argv, cwd=str(root))
    if rc != 0 or not out_json.exists():
        return result("gitleaks", "FAILED", note="gitleaks exit %s: %s" % (rc, (se or so).strip()[-300:]), version=pinned_version("gitleaks"))
    items = json.loads(out_json.read_text(encoding="utf-8") or "[]")
    findings = parse_gitleaks(items, root)
    # raw report on disk: keep only locations and rule ids (the values are already redacted by --redact; message, author
    # and e-mail are dropped too)
    write_json(out_json, [{k: it[k] for k in GITLEAKS_RAW_KEEP if k in it} for it in items])
    note = "full git history (diffs of every commit)" if history else "working tree (archives opened to depth 2)"
    return result("gitleaks-history" if history else "gitleaks", "OK", findings, note, pinned_version("gitleaks"))



# -------------------------------------------------------------------------------------------------------------- deps

def find_locks(root):
    root = Path(root)
    py = sorted(root.glob("whynot-cut/setup/locks/*.lock")) + sorted(root.glob("tools/security/*.lock"))
    npm = sorted(Path(p) for p in walk_files(root) if os.path.basename(p) == "package-lock.json")  # never through a junction
    return py, npm


def pip_audit_argv(lock, out_json):
    return [str(tool_exe("pip-audit")), "-r", str(lock), "--require-hashes", "--disable-pip", "--no-deps", "-f", "json",
            "-o", str(out_json)]


def parse_pip_audit(data, lock, root):
    out = []
    f = rel(lock, root)
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            ids = [v["id"]] + list(v.get("aliases", []))
            fixes = ",".join(v.get("fix_versions", [])) or "no fix yet"
            out.append(finding("pip-audit", v["id"], "HIGH", f, 0,
                               "%s==%s: %s (fix: %s)" % (dep["name"], dep["version"], "/".join(ids[:3]), fixes),
                               "%s==%s:%s" % (dep["name"], dep["version"], v["id"])))
    return out


def scan_pip_audit(root, raw_dir, locks):
    miss = need("pip-audit")
    if miss:
        return miss
    if not locks:
        return result("pip-audit", "FAILED", note="no Python lock file found under %s (expected whynot-cut/setup/locks/*.lock): "
                      "nothing was audited" % root, version=pinned_version("pip-audit"))
    findings, notes, status, codes = [], [], "OK", []
    for i, lock in enumerate(locks):
        out_json = Path(raw_dir) / ("pip-audit-%d.json" % i)
        if out_json.exists():
            out_json.unlink()  # a stale file of an earlier run must never be read as this run's result
        rc, so, se = run(pip_audit_argv(lock, out_json), cwd=str(root))
        if not out_json.exists() or rc not in (0, 1):
            return result("pip-audit", "FAILED", findings, "pip-audit exit %s on %s: %s" % (rc, lock.name, (se or so).strip()[-300:]),
                          pinned_version("pip-audit"))
        data = json.loads(out_json.read_text(encoding="utf-8"))
        skipped = [d for d in data.get("dependencies", []) if "skip_reason" in d]
        if skipped:
            status = "DEGRADED"
            codes.append("skipped-requirements")
            notes.append("%s: %d requirement(s) NOT audited (%s)" % (lock.name, len(skipped), skipped[0]["skip_reason"][:80]))
        findings += parse_pip_audit(data, lock, root)
    return result("pip-audit", status, findings, "; ".join(notes) or "%d lock(s)" % len(locks), pinned_version("pip-audit"), codes)


def osv_argv(locks_py, locks_npm, out_json, root):
    argv = [str(tool_exe("osv-scanner")), "scan", "source", "--no-resolve", "--format", "json", "--output-file", str(out_json)]
    for l in locks_py:
        argv += ["-L", "requirements.txt:%s" % l]
    for l in locks_npm:
        argv += ["-L", "package-lock.json:%s" % l]
    return argv


def parse_osv(data, root):
    out = []
    for res in data.get("results", []):
        src = rel(res.get("source", {}).get("path", ""), root)
        for pkg in res.get("packages", []):
            p = pkg["package"]
            sev_by_id = {}
            for g in pkg.get("groups", []):
                for i in g.get("ids", []):
                    sev_by_id[i] = g.get("max_severity")
            for v in pkg.get("vulnerabilities", []):
                sev = cvss_to_sev(sev_by_id.get(v["id"]))
                out.append(finding("osv-scanner", v["id"], sev, src, 0,
                                   "%s %s: %s" % (p["name"], p["version"], (v.get("summary") or v.get("details") or "")[:120]),
                                   "%s==%s:%s" % (p["name"], p["version"], v["id"])))
    return out


def scan_osv(root, raw_dir, locks_py, locks_npm):
    miss = need("osv-scanner")
    if miss:
        return miss
    if not (locks_py or locks_npm):
        return result("osv-scanner", "FAILED", note="no lock file found under %s: nothing was scanned" % root, version=pinned_version("osv-scanner"))
    out_json = Path(raw_dir) / "osv.json"
    if out_json.exists():
        out_json.unlink()
    rc, so, se = run(osv_argv(locks_py, locks_npm, out_json, root), cwd=str(root))
    if rc not in (0, 1) or not out_json.exists():
        return result("osv-scanner", "FAILED", note="osv-scanner exit %s: %s" % (rc, (se or so).strip()[-300:]), version=pinned_version("osv-scanner"))
    return result("osv-scanner", "OK", parse_osv(json.loads(out_json.read_text(encoding="utf-8")), root),
                  "%d lock(s)" % (len(locks_py) + len(locks_npm)), pinned_version("osv-scanner"))


NPM_SEV = {"critical": "CRITICAL", "high": "HIGH", "moderate": "MEDIUM", "low": "LOW", "info": "INFO"}


def parse_npm_audit(data, label, lock="adobe/package-lock.json"):
    out = []
    for name, v in (data.get("vulnerabilities") or {}).items():
        sev = NPM_SEV.get(v.get("severity"), "HIGH")
        via = [x["title"] if isinstance(x, dict) else x for x in v.get("via", [])]
        out.append(finding("npm-audit", "%s:%s" % (label, name), sev, lock, 0,
                           "%s (%s): %s" % (name, v.get("range", ""), "; ".join(str(x) for x in via)[:140]),
                           "%s:%s:%s" % (label, name, v.get("range", ""))))
    return out


def scan_npm(root):
    root = Path(root)
    adobe = root / "adobe"
    if not (adobe / "package-lock.json").exists():
        return result("npm-audit", "OK", note="no adobe/package-lock.json")
    npm = which_safe("npm")
    if not npm:
        return result("npm-audit", "MISSING", note="MISSING npm (not found on PATH)")
    findings = []
    for label, extra in (("prod", ["--omit=dev"]), ("all", [])):
        rc, so, se = run([npm, "audit", "--json", "--package-lock-only"] + extra, cwd=str(adobe))
        try:
            data = json.loads(so)
        except ValueError:
            return result("npm-audit", "FAILED", findings, "npm audit (%s) gave no JSON, exit %s: %s" % (label, rc, se.strip()[-200:]))
        if "error" in data and "vulnerabilities" not in data:
            return result("npm-audit", "FAILED", findings, "npm audit (%s): %s" % (label, str(data["error"].get("summary", ""))[:200]))
        findings += parse_npm_audit(data, label)
    return result("npm-audit", "OK", findings, "prod + full", None)


# ------------------------------------------------------------------------------------------------ lock-hash check

def check_locks(root):
    """Every pip lock requirement has a sha256 hash; every package-lock entry that has a download URL has `integrity`
    (sha256/384/512). Zero locks found is a failure, not a pass."""
    from install_tools import lock_lines_without_hash  # stdlib-only sibling
    root = Path(root)
    py, npm = find_locks(root)
    if not (py or npm):
        return result("lock-hash", "FAILED", note="no lock file found under %s (expected whynot-cut/setup/locks/*.lock, "
                      "package-lock.json): nothing was checked" % root)
    problems = []
    for l in py:
        text = l.read_text(encoding="utf-8")
        if not parse_requirements_lock(text):
            problems.append("%s: lock file with no pinned requirement (empty or unreadable lock: nothing would be audited)" % rel(l, root))
        for bad in lock_lines_without_hash(text):
            problems.append("%s: requirement without --hash=sha256:<64 hex> %s" % (rel(l, root), bad))
    for l in npm:
        try:
            data = json.loads(l.read_text(encoding="utf-8"))
        except ValueError:
            problems.append("%s: not valid JSON" % rel(l, root))
            continue
        if not isinstance(data, dict) or not data.get("packages"):
            problems.append("%s: no `packages` map (lockfileVersion 1 or empty): its entries cannot be checked" % rel(l, root))
            continue
        for key, e in data["packages"].items():
            if key and e.get("resolved") and not e.get("link"):
                integ = e.get("integrity") or ""
                if not integ:
                    problems.append("%s: %s has no integrity" % (rel(l, root), key))
                elif not integ.startswith(NPM_INTEGRITY):
                    problems.append("%s: %s integrity is not sha256/384/512" % (rel(l, root), key))
    findings = [finding("lock-hash", "missing-hash", "HIGH", p.split(": ")[0], 0, p, p) for p in problems]
    return result("lock-hash", "OK", findings, "%d pip lock(s), %d npm lock(s)" % (len(py), len(npm)))


# ------------------------------------------------------------------------------------------------------------- SBOM

def parse_requirements_lock(text):
    comps = []
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", line.strip())
        if m:
            comps.append((m.group(1).lower().replace("_", "-"), m.group(2)))
    return comps


def build_sbom(root):
    root = Path(root)
    py, npm = find_locks(root)
    comps, seen = [], set()
    for l in py:
        for name, ver in parse_requirements_lock(l.read_text(encoding="utf-8")):
            purl = "pkg:pypi/%s@%s" % (name, ver)
            if purl not in seen:
                seen.add(purl)
                comps.append({"type": "library", "name": name, "version": ver, "purl": purl, "bom-ref": purl})
    for l in npm:
        try:
            data = json.loads(l.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for key, e in (data.get("packages") or {}).items():
            if not key or "node_modules/" not in key or not e.get("version"):
                continue
            name = key.split("node_modules/")[-1]
            purl = "pkg:npm/%s@%s" % (name.replace("@", "%40", 1) if name.startswith("@") else name, e["version"])
            if purl in seen:
                continue
            seen.add(purl)
            c = {"type": "library", "name": name, "version": e["version"], "purl": purl, "bom-ref": purl}
            integ = e.get("integrity", "")
            if integ.startswith("sha512-"):
                c["hashes"] = [{"alg": "SHA-512", "content": base64.b64decode(integ[7:]).hex()}]
            comps.append(c)
    return {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "component": {"type": "application", "name": "whynot-cut", "version": "3.0-dev"},
                         "tools": {"components": [{"type": "application", "name": "tools/security/scan.py"}]}},
            "components": comps}


def scan_sbom(root, raw_dir):
    bom = build_sbom(root)
    if not bom["components"]:
        return result("sbom", "FAILED", note="no components found under %s (no lock files?)" % root)
    write_json(Path(raw_dir) / "sbom.cdx.json", bom)
    return result("sbom", "OK", note="%d components (Python locks + npm); binaries and models join in L-T9" % len(bom["components"]))


# ------------------------------------------------------------------------------------------------- orchestration

def run_scans(modes, root, raw_dir, offline=False, history=False, registry=True):
    results = []
    locks_py, locks_npm = find_locks(root)
    if "sast" in modes:
        results.append(scan_semgrep(root, raw_dir, offline, registry))
        results.append(scan_bandit(root, raw_dir))
        results.append(scan_eslint(root, raw_dir))
    if "secrets" in modes:
        results.append(scan_gitleaks(root, raw_dir, history=False))
    if "locks" in modes:
        results.append(check_locks(root))
    if "deps" in modes:
        if offline:
            for t in ("pip-audit", "osv-scanner", "npm-audit"):
                results.append(result(t, "DEGRADED", note="DEGRADED: offline, vulnerability databases NOT checked", codes=["offline"]))
        else:
            results.append(scan_pip_audit(root, raw_dir, locks_py))
            results.append(scan_osv(root, raw_dir, locks_py, locks_npm))
            results.append(scan_npm(root))
    if "sbom" in modes:
        results.append(scan_sbom(root, raw_dir))
    return results


def exit_code(results, new_blocking):
    if new_blocking:
        return EXIT_FINDINGS
    if any(r["status"] in ("MISSING", "MISMATCH", "ALTERED", "FAILED") for r in results):
        return EXIT_TOOL
    if any(r["status"] == "DEGRADED" and not r.get("accepted_gap") for r in results):
        return EXIT_DEGRADED
    return EXIT_OK


def render_report(results, new, accepted, expired, gate, root, today, baseline=None):
    L = ["# Security scan: %s (%s)" % (gate, today.isoformat()), "",
         "Generated by `tools/security/scan.py`. Secret values are never written here (file, line, rule, commit only).", "",
         "## Scanners", "", "| Scanner | Version | Status | Findings | Note |", "|---|---|---|---|---|"]
    for r in results:
        status = r["status"] + (" (accepted gap: %s; %s, review %s)" % (r["accepted_gap"]["reason"], r["accepted_gap"]["owner_task"],
                                                                         r["accepted_gap"]["review_date"]) if r.get("accepted_gap") else "")
        L.append("| %s | %s | %s | %d | %s |" % (r["tool"], r["version"] or "-", status.replace("|", "/"), len(r["findings"]),
                                                 (r["note"] or "").replace("|", "/")))
    counts = {s: 0 for s in SEV_ORDER}
    for r in results:
        for f in r["findings"]:
            counts[f["severity"]] += 1
    L += ["", "## Findings by severity (all, before the baseline)", "",
          " | ".join("%s %d" % (s, counts[s]) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")), "",
          "## New High/Critical (not in the baseline): %d" % len([f for f in new if f["severity"] in BLOCKING]), ""]
    for f in sorted(new, key=lambda f: -SEV_ORDER[f["severity"]]):
        if f["severity"] in BLOCKING:
            L.append("- **%s** `%s` %s:%s %s%s" % (f["severity"], f["rule"], f["file"], f["line"], f["message"],
                                                    " (commit %s)" % f["commit"] if f.get("commit") else ""))
    L += ["", "## Accepted by the baseline: %d" % len(accepted), ""]
    verdicts = {}
    for f in accepted:
        v = (baseline or {}).get(f["fingerprint"], {}).get("verdict", "unspecified")
        verdicts[v] = verdicts.get(v, 0) + 1
    if verdicts:
        L += [", ".join("%s %d" % kv for kv in sorted(verdicts.items())), ""]
    for f in accepted:
        e = (baseline or {}).get(f["fingerprint"], {})
        if e.get("verdict") == "real":
            L.append("- REAL, fix with its owner (%s): `%s` %s:%s: %s" % (e.get("owner_task", "?"), f["rule"], f["file"], f["line"], e.get("reason", "")))
    for e in expired:
        L.append("- REVIEW OVERDUE (%s): %s %s in %s" % (e["review_date"], e["tool"], e["rule"], e["file"]))
    L += ["", "## Not blocking (Medium and below, new): %d" % len([f for f in new if f["severity"] not in BLOCKING]), ""]
    for f in sorted([f for f in new if f["severity"] not in BLOCKING], key=lambda f: (-SEV_ORDER[f["severity"]], f["file"]))[:200]:
        L.append("- %s `%s` %s:%s" % (f["severity"], f["rule"], f["file"], f["line"]))
    return "\n".join(L) + "\n"


def _utf8_streams():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _utf8_streams()
    try:
        return _main(argv)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001  any crash is a failed scan (exit 4), never a Python traceback that reads as exit 1
        print("SCAN ERROR: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return EXIT_TOOL


def _main(argv):
    ap = argparse.ArgumentParser(prog="scan.py", description=__doc__.split("\n")[0])
    for m in ("all", "sast", "secrets", "deps", "sbom", "locks"):
        ap.add_argument("--" + m, action="store_true")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--gate", default="manual")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-registry", action="store_true")
    ap.add_argument("--baseline", default=str(REPO / "docs" / "security" / "baseline.json"))
    ap.add_argument("--out", default=str(REPO / "docs" / "security"))
    ap.add_argument("--raw", default=str(REPO / "dist"))
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args(argv)
    modes = {m for m in ("sast", "secrets", "deps", "sbom", "locks") if getattr(a, m) or a.all}
    if not modes:
        ap.print_usage(sys.stderr)
        print("choose --all or at least one of --sast --secrets --deps --sbom --locks", file=sys.stderr)
        return EXIT_USAGE
    try:
        baseline, gaps = load_baseline_full(a.baseline)
    except BaselineError as e:
        print("BASELINE ERROR:", e, file=sys.stderr)
        return EXIT_USAGE
    today = datetime.date.today()
    raw_dir = Path(a.raw) / ("scan-%s-%s" % (today.isoformat(), re.sub(r"[^A-Za-z0-9_.-]", "_", a.gate)))
    raw_dir.mkdir(parents=True, exist_ok=True)
    offline = is_offline(a.offline) if "deps" in modes or "sast" in modes else False
    results = run_scans(modes, Path(a.root), raw_dir, offline=offline, history=a.history, registry=not a.no_registry)
    apply_known_gaps(results, gaps)
    allf = [f for r in results for f in r["findings"]]
    new, accepted, expired = split_by_baseline(allf, baseline, today)
    new_blocking = [f for f in new if f["severity"] in BLOCKING]
    code = exit_code(results, new_blocking)
    write_json(raw_dir / "findings.json", {"results": [{k: v for k, v in r.items() if k != "findings"} for r in results],
                                           "findings": allf})
    if not a.no_report:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / ("scan-%s-%s.md" % (today.isoformat(), re.sub(r"[^A-Za-z0-9_.-]", "_", a.gate)))).write_text(
            render_report(results, new, accepted, expired, a.gate, a.root, today, baseline), encoding="utf-8")
    Path(a.raw).mkdir(parents=True, exist_ok=True)
    write_json(Path(a.raw) / "security-last-run.json", {"date": today.isoformat(), "gate": a.gate, "modes": sorted(modes), "exit": code})
    for r in results:
        gap = " [accepted gap]" if r.get("accepted_gap") else ""
        print("%-17s %-9s %3d finding(s)  %s%s" % (r["tool"], r["status"], len(r["findings"]), r["note"], gap))
    print("new High/Critical: %d | accepted by baseline: %d | exit %d" % (len(new_blocking), len(accepted), code))
    for f in new_blocking[:50]:
        print("  NEW %s %s %s:%s %s" % (f["severity"], f["rule"], f["file"], f["line"], f["message"][:120]))
    return code


if __name__ == "__main__":
    sys.exit(main())
