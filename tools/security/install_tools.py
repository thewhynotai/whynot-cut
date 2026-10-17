#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Install the pinned security scanners per user (Addendum L §L3, Phase 4 Task 39 / L-T1). Stdlib only.

  python tools/security/install_tools.py            install what is missing (idempotent), then verify everything
  python tools/security/install_tools.py --check    verify only (no network); exit 1 if anything is missing or altered

Rules (the owner's house rules for the scanner lane):
  * free, official sources only (GitHub release assets and PyPI), pinned in versions.json;
  * every download is checked against the sha256 pinned in versions.json BEFORE anything is written to the tools home;
  * per user, under the tools home (default D:/ClaudeData/tools/security, override WNC_SEC_TOOLS): no admin, no system
    install, no PATH change, no registry write;
  * the Python tools go into their own venv from the hashed dev lock (`pip install --require-hashes --no-deps`);
  * no telemetry switch is turned on, and nothing of ours is uploaded: this script only downloads.
"""
import base64
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


class InstallError(Exception):
    pass


def versions():
    return json.loads((HERE / "versions.json").read_text(encoding="utf-8"))


def platform_key():
    sysname = platform.system().lower()
    if sysname == "windows":
        return "win-x64"
    if sysname == "linux":
        return "linux-x64"
    raise InstallError("unsupported platform %r (L-T1 supports Windows x64 and Linux x64)" % sysname)


def tools_home(v=None):
    env = os.environ.get("WNC_SEC_TOOLS")
    if env:
        return Path(env)
    v = v or versions()
    return Path(v["tools_home_default"])


def lock_lines_without_hash(text):
    """Requirement lines of a pip lock that carry no `--hash=sha256:` (continuation lines are joined first)."""
    bad = []
    logical, first = [], None
    for raw in text.splitlines() + [""]:
        line = raw.rstrip()
        stripped = line.strip()
        if not logical and (not stripped or stripped.startswith("#")):
            continue
        if not logical:
            first = stripped
        logical.append(stripped)
        if line.endswith("\\"):
            continue
        joined = " ".join(logical)
        digests = re.findall(r"--hash=sha256:(\S*)", joined)
        if not digests or not all(re.fullmatch(r"[0-9a-f]{64}", d) for d in digests):  # at least one, and every one well-formed
            bad.append(first.rstrip("\\").strip())
        logical = []
    return bad


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wnc-security-install/1"})
    with urllib.request.urlopen(req, timeout=120) as r:  # default context: certificate verification ON
        return r.read()


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _manifest_path(home):
    return Path(home) / "manifest.json"


def _load_manifest(home):
    """The install manifest as {tool: {exe, exe_sha256, ...}}; anything that is not that shape reads as an empty manifest
    (the tool then reports as not installed), never as an exception."""
    p = _manifest_path(home)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _extract(data, spec):
    kind, member = spec["archive"], spec.get("member")
    if kind == "raw":
        return data
    if kind == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if member not in z.namelist():  # exact name only: never a traversal path, never extractall
                raise InstallError("archive has no member %r" % member)
            return z.read(member)
    if kind == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            m = next((x for x in t.getmembers() if x.name == member and x.isfile()), None)
            if m is None:
                raise InstallError("archive has no member %r" % member)
            return t.extractfile(m).read()
    raise InstallError("unknown archive kind %r" % kind)


def install_binary(name, version, spec, home, fetch=_http_get):
    """Download spec['url'], verify its sha256 against the pin, extract only the named member into <home>/bin."""
    data = fetch(spec["url"])
    got = _sha(data)
    if got != spec["sha256"]:
        raise InstallError("%s %s: sha256 mismatch for %s (pinned %s, got %s); nothing was installed"
                           % (name, version, spec["url"], spec["sha256"], got))
    exe_bytes = _extract(data, spec)
    home = Path(home)
    bindir = home / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    exe = bindir / spec["exe"]
    tmp = exe.with_name(exe.name + ".part")
    tmp.write_bytes(exe_bytes)
    os.replace(tmp, exe)
    if os.name != "nt":
        exe.chmod(0o755)
    man = _load_manifest(home)
    man[name] = {"version": version, "archive_sha256": got, "exe": str(spec["exe"]), "exe_sha256": _sha(exe_bytes)}
    _manifest_path(home).write_text(json.dumps(man, indent=1), encoding="utf-8")
    return exe


def verify_installed(name, home):
    """None when the binary is installed and unaltered, else a one-line reason. Three checks: the file the scanner will
    run is the one the manifest names, its bytes match the manifest, and (when versions.json pins one) the manifest's
    sha256 is the pinned sha256 of the official release's executable, so a rewritten manifest does not self-attest."""
    home = Path(home)
    man = _load_manifest(home).get(name)
    if not man:
        return "%s is not installed under %s" % (name, home)
    try:
        spec = versions()["binaries"][name]["platforms"][platform_key()]
    except (KeyError, InstallError):
        spec = {}
    exe_name, want = man.get("exe"), man.get("exe_sha256")
    if not isinstance(exe_name, str) or not isinstance(want, str) or os.sep in exe_name or "/" in exe_name or exe_name in ("", ".", ".."):
        return "%s: the install manifest is malformed (re-run install_tools.py)" % name
    if spec.get("exe") and exe_name != spec["exe"]:
        return "%s: the manifest names %s but the pinned program is %s" % (name, exe_name, spec["exe"])
    exe = home / "bin" / exe_name
    if not exe.is_file():
        return "%s: %s is missing or not a file" % (name, exe)
    try:
        got = _sha(exe.read_bytes())
    except OSError as e:
        return "%s: %s cannot be read (%s)" % (name, exe, e)
    if got != want:
        return "%s: %s differs from the installed sha256 (altered after install)" % (name, exe)
    if spec.get("exe_sha256") and want != spec["exe_sha256"]:
        return "%s: the installed sha256 is not the pinned sha256 of the official executable" % name
    return None


def venv_python(home):
    home = Path(home)
    for c in (home / "venv" / "Scripts" / "python.exe", home / "venv" / "bin" / "python"):
        if c.exists():
            return c
    return None


UNSAFE_ENV = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "NODE_OPTIONS", "NODE_TLS_REJECT_UNAUTHORIZED",
              "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML",
              "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "PIP_CERT", "PIP_NO_VERIFY", "PIP_FIND_LINKS", "PIP_CONFIG_FILE",
              "NODE_EXTRA_CA_CERTS", "NODE_PATH", "PYTHONUSERBASE", "PYTHONBREAKPOINT", "SSLKEYLOGFILE", "LD_PRELOAD", "LD_LIBRARY_PATH",
              "DYLD_INSERT_LIBRARIES", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_EXEC_PATH", "GIT_CONFIG", "GIT_CONFIG_GLOBAL",
              "GIT_CONFIG_SYSTEM", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS")


def safe_env(base=None):
    """The caller's environment without the variables that can redirect code, weaken TLS or add a package index to a
    scanner or to pip (the integrity check would not see them). Proxy settings are kept."""
    return {k: v for k, v in (os.environ if base is None else base).items() if k.upper() not in UNSAFE_ENV}


def _pip_env(home):
    """pip's cache stays inside the tools home (per user, on D:), never in the profile folder."""
    env = safe_env()
    env.update(PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CACHE_DIR=str(Path(home) / "cache" / "pip"))
    return env


def _site_packages(home):
    v = Path(home) / "venv"
    for c in [v / "Lib" / "site-packages"] + sorted((v / "lib").glob("python*/site-packages")):
        if c.is_dir():
            return c
    return None


def _record_problem(sp, dist):
    """None when every hashed file of this dist-info's RECORD is unchanged; a RECORD with no hash at all is a problem."""
    bad, hashed = [], 0
    for line in (dist / "RECORD").read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.rsplit(",", 2)
        if len(parts) != 3 or not parts[1].startswith("sha256="):
            continue
        rel_path, algo = parts[0], parts[1]
        if rel_path.endswith(".pyc"):
            continue
        hashed += 1
        f = (sp / rel_path).resolve()
        try:
            digest = base64.urlsafe_b64encode(hashlib.sha256(f.read_bytes()).digest()).rstrip(b"=").decode("ascii")
        except OSError:
            bad.append(rel_path + " (missing)")
            continue
        if digest != algo[len("sha256="):]:
            bad.append(rel_path)
        if len(bad) >= 3:
            break
    if not hashed:
        return "%s has no hashed files in its RECORD" % dist.name
    return ("%d installed file(s) of %s differ from the wheel's RECORD (altered after install), first: %s"
            % (len(bad), dist.name, bad[0])) if bad else None


def _norm_dist(s):
    return re.sub(r"[-_.]+", "_", s).lower()


def verify_python_tool(name, home, everything=False):
    """None when the tool's wheel is intact: every file pip wrote for it is byte-identical to its RECORD hash. With
    everything=True the same is checked for EVERY package of the tools venv (the dependencies run in the tool's process
    too). Catches a replaced launcher, a patched module, a swapped native binary, a planted file replacing a dependency."""
    sp = _site_packages(home)
    if sp is None:
        return "%s: tools venv not found under %s" % (name, home)
    dists = sorted(sp.glob("*.dist-info"))
    mine = [d for d in dists if _norm_dist(d.name[:-len(".dist-info")].rsplit("-", 1)[0]) == _norm_dist(name)]
    if not mine:
        return "%s: not installed in the tools venv" % name
    for d in (dists if everything else mine):
        try:
            bad = _record_problem(sp, d)
        except (OSError, ValueError) as e:
            bad = "%s: RECORD unreadable (%s)" % (d.name, e)
        if bad:
            return "%s: %s" % (name, bad)
    if everything:  # a file that runs at interpreter start-up but belongs to no installed wheel
        known = set()
        for d in dists:
            try:
                for line in (d / "RECORD").read_text(encoding="utf-8", errors="replace").splitlines():
                    known.add(line.rsplit(",", 2)[0].replace("\\", "/"))
            except OSError:
                continue
        for f in list(sp.glob("*.pth")) + list(sp.glob("sitecustomize*")) + list(sp.glob("usercustomize*")):
            if f.name not in known:
                return "%s: %s is in site-packages but belongs to no installed package (runs at start-up)" % (name, f.name)
    return None


def install_venv(home, base_python=None):
    v = versions()
    lock = REPO / v["python_tools"]["lock"]
    if _sha(lock.read_bytes()) != v["python_tools"]["lock_sha256"]:
        raise InstallError("dev lock differs from the sha256 in versions.json; refusing to install")
    missing = lock_lines_without_hash(lock.read_text(encoding="utf-8"))
    if missing:
        raise InstallError("dev lock has unhashed requirements: %s" % ", ".join(missing[:5]))
    home = Path(home)
    py = venv_python(home)
    if py is None:
        subprocess.run([base_python or sys.executable, "-m", "venv", str(home / "venv")], check=True)
        py = venv_python(home)
    subprocess.run([str(py), "-m", "pip", "install", "--require-hashes", "--no-deps", "--only-binary", ":all:",
                    "-r", str(lock)], check=True, env=_pip_env(home))
    return py


def check_all(home=None):
    """Problems (list of strings) for every pinned tool; empty list = all installed and unaltered."""
    v = versions()
    home = Path(home) if home else tools_home(v)
    problems = []
    for name in v["binaries"]:
        p = verify_installed(name, home)
        if p:
            problems.append(p)
    if venv_python(home) is None:
        problems.append("python tools venv is missing under %s" % home)
    else:
        for pkg in ("semgrep", "bandit", "pip-audit"):
            p = verify_python_tool(pkg, home, everything=(pkg == "semgrep"))
            if p:
                problems.append(p)
    return problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    v = versions()
    home = tools_home(v)
    if "--check" in argv:
        probs = check_all(home)
        for p in probs:
            print("PROBLEM:", p)
        print("tools home:", home)
        return 1 if probs else 0
    key = platform_key()
    home.mkdir(parents=True, exist_ok=True)
    for name, b in v["binaries"].items():
        if verify_installed(name, home) is None and _load_manifest(home)[name]["version"] == b["version"]:
            print("ok   %s %s (already installed)" % (name, b["version"]))
            continue
        exe = install_binary(name, b["version"], b["platforms"][key], home)
        print("done %s %s -> %s" % (name, b["version"], exe))
    py = install_venv(home)
    print("done python tools venv ->", py)
    probs = check_all(home)
    for p in probs:
        print("PROBLEM:", p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
