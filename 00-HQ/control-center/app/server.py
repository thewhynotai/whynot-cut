"""WhyNot Control Center dashboard server: http://127.0.0.1:<port>/ (this PC only, token-protected).

    python -X utf8 server.py            # start (or say it already runs); prints the URL
    python -X utf8 server.py --url      # print the URL of the running server and exit (code 1 if none)

How it stays light and token-free: every `watch_seconds` it only stats the files it reads; it rebuilds the snapshot
when one changed, after every slow refresh (`slow_seconds`) and at the latest every `full_minutes`. Clients get a
push only when the snapshot really changed. No model is ever called.
"""
import hashlib, hmac, http.server, json, os, queue, secrets, sys, threading, time, traceback, urllib.parse, urllib.request
from pathlib import Path

import common
import actions, collect, history, ownermsg

STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
          "/logo.svg": ("logo.svg", "image/svg+xml"), "/favicon.png": ("favicon.png", "image/png")}


class Hub:
    """Holds the newest snapshot and pushes it to open pages."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.col = collect.Collector(cfg)
        self.snap, self.version, self.digest, self.built = None, 0, "", 0.0
        self.clients = set()
        self.lock = threading.Lock()
        self.hist = str(common.state_path(cfg, "history.jsonl"))
        self.log = str(common.state_path(cfg, "server.log"))
        self.stamp = None
        self.last_error = None
        self.csrf = secrets.token_urlsafe(24)  # per server run; the page fetches it with its cookie
        self.actions = actions.Actions(cfg)

    def note(self, msg):
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")

    def watched(self):
        hqd = common.HQ
        paths = [hqd / "BOARD.md", hqd / "intake" / "state.json", hqd / "PRIMARY_ACCOUNT_INBOX.md",
                 hqd / "inbox" / "h1", hqd / "inbox" / "h2", hqd / "reviews", hqd / "tasks"]
        paths += list((hqd / "tasks").glob("*.md"))
        for a in self.cfg["accounts"]:
            if a["kind"] == "helper":
                auto = Path(a["profile"], "auto")
                paths += [auto / "status.json", auto / "auto.log", Path(self.cfg["state_dir"], "mailbox", a["id"], "pending"),
                          Path(self.cfg["state_dir"], "mailbox", a["id"], "delivered")]
                try:
                    log = json.loads((auto / "status.json").read_text(encoding="utf-8")).get("log")
                    if log:
                        paths.append(Path(log))
                except (OSError, ValueError):
                    pass
        paths += [Path(p) for p in collect.glob.glob(str(collect.al.APP_SESSIONS / "*" / "*" / "local_*.json"))]
        out = []
        for p in paths:
            try:
                st = os.stat(p)
                out.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                out.append((str(p), 0, 0))
        return hashlib.sha1(repr(out).encode()).hexdigest()

    def save(self, snap):
        """<state>\\snapshot.json: what the terminals and the status line read (no HTTP needed)."""
        path = str(common.state_path(self.cfg, "snapshot.json"))
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(snap, f, default=str)
        os.replace(path + ".tmp", path)

    def rebuild(self, why):
        """A failed build raises before anything is saved, so snapshot.json keeps its true (old) generated_at."""
        changed = self._rebuild(why)
        with self.lock:
            snap = self.snap
        self.save(snap)
        return changed

    def _rebuild(self, why):
        snap = self.col.build()
        body = {k: v for k, v in snap.items() if k != "generated_at"}
        digest = hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        with self.lock:
            prev = self.snap
            self.built = time.time()
            snap["refresh"] = {"why": why, "built_at": snap["generated_at"], "version": self.version,
                               "watch_seconds": self.cfg["refresh"]["watch_seconds"],
                               "slow_seconds": self.cfg["refresh"]["slow_seconds"],
                               "full_minutes": self.cfg["refresh"]["full_minutes"],
                               "stale_minutes": self.cfg["refresh"]["stale_minutes"]}
            if digest == self.digest and prev:
                prev["generated_at"] = snap["generated_at"]  # still true now: the page's "last sync" moves on
                prev["refresh"].update(built_at=snap["generated_at"], why=why)
                return False
            self.version += 1
            snap["refresh"]["version"] = self.version
            self.snap, self.digest = snap, digest
        history.append(self.hist, history.transitions(prev, snap))
        self.push(snap)
        return True

    def push(self, snap):
        data = json.dumps(snap, default=str)
        for q in list(self.clients):
            for _ in range(2):
                try:
                    q.put_nowait(data)
                    break
                except queue.Full:
                    try:
                        q.get_nowait()  # a slow page: drop its oldest, keep the newest
                    except queue.Empty:
                        pass

    def run(self):
        r = self.cfg["refresh"]
        last_slow = 0.0
        while True:
            try:
                why = None
                if time.time() - last_slow >= r["slow_seconds"]:
                    self.col.refresh_slow()
                    last_slow = time.time()
                    why = "periodic check (heavy queue, git, loops)"
                stamp = self.watched()
                if stamp != self.stamp:
                    self.stamp, why = stamp, why or "a watched file changed"
                if not why and time.time() - self.built >= r["full_minutes"] * 60:
                    why = "full refresh"
                if why or self.snap is None:
                    self.rebuild(why or "start")
            except Exception:  # noqa: BLE001  the loop must survive a reader hiccup
                err = traceback.format_exc()
                if err != self.last_error:  # the same failure every 5 s is logged once
                    self.note("refresh error:\n" + err)
                self.last_error = err
            else:
                self.last_error = None
            time.sleep(r["watch_seconds"])


def make_handler(hub, token, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "WhyNotCC"

        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
                                                        "style-src 'self' https://fonts.googleapis.com; "
                                                        "font-src https://fonts.gstatic.com")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def authed(self):
            cookie = self.headers.get("Cookie") or ""
            return any(hmac.compare_digest(c.strip().encode(), f"wnc_cc={token}".encode()) for c in cookie.split(";"))

        def do_GET(self):  # noqa: N802
            if self.headers.get("Host") not in allowed_hosts:
                return self.send(403, "forbidden host", "text/plain")
            url = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(url.query)
            if url.path == "/whoami":  # no key needed, reveals nothing secret: lets the launcher tell us from a stranger
                return self.send(200, json.dumps({"app": "WhyNotCC", "pid": os.getpid()}))
            if url.path == "/" and qs.get("t", [""])[0] == token:
                return self.send(303, "", "text/plain", {
                    "Location": "/", "Set-Cookie": f"wnc_cc={token}; HttpOnly; SameSite=Strict; Path=/"})
            if not self.authed():
                return self.send(401, "Open the dashboard from the WhyNot Control Center shortcut (it carries the key).",
                                 "text/plain; charset=utf-8")
            if url.path in STATIC:
                name, ctype = STATIC[url.path]
                return self.send(200, (common.WEB / name).read_bytes(), ctype)
            if url.path == "/api/state":
                with hub.lock:
                    snap = hub.snap
                return self.send(200, json.dumps(snap or {"loading": True}, default=str))
            if url.path == "/api/history":
                g = lambda k: qs.get(k, [""])[0]  # noqa: E731
                return self.send(200, json.dumps(history.search(hub.hist, g("q"), g("account"), g("task"))))
            if url.path == "/api/messages":
                acct = qs.get("account", [""])[0]
                try:
                    return self.send(200, json.dumps(ownermsg.recent(hub.cfg["state_dir"], acct, 20)))
                except ValueError:
                    return self.send(400, "[]")
            if url.path == "/api/csrf":
                return self.send(200, json.dumps({"csrf": hub.csrf}))
            if url.path == "/api/stream":
                return self.stream()
            return self.send(404, "not found", "text/plain")

        def do_POST(self):  # noqa: N802
            """Buttons only. Needs: right Host, the page cookie, a local Origin, and the per-run CSRF token."""
            try:  # read the (small) body first: answering before it is read makes Windows reset the connection
                raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096))
            except (ValueError, OSError):
                raw = b""
            if self.headers.get("Host") not in allowed_hosts:
                return self.send(403, "forbidden host", "text/plain")
            if not self.authed():
                return self.send(401, json.dumps({"ok": False}))
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.send(403, json.dumps({"ok": False, "msg": "foreign origin"}))
            if not hmac.compare_digest((self.headers.get("X-CC-CSRF") or "").encode(), hub.csrf.encode()):
                return self.send(403, json.dumps({"ok": False, "msg": "missing or wrong CSRF token"}))
            if urllib.parse.urlparse(self.path).path != "/api/action":
                return self.send(404, json.dumps({"ok": False}))
            try:
                body = json.loads(raw or b"{}")
                name, acct = str(body.get("action", "")), str(body.get("account", ""))
            except (ValueError, AttributeError):
                return self.send(400, json.dumps({"ok": False}))
            out = hub.actions.perform(name, acct)
            history.append(hub.hist, [{"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "action", "account": acct,
                                       "task": "", "text": f"Button '{name}' for {acct}: {out['msg']}"}])
            return self.send(200, json.dumps(out, ensure_ascii=False))

        def stream(self):
            q = queue.Queue(maxsize=4)
            hub.clients.add(q)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with hub.lock:
                    snap = hub.snap
                if snap:
                    self.wfile.write(f"event: snapshot\ndata: {json.dumps(snap, default=str)}\n\n".encode())
                    self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=20)
                        self.wfile.write(f"event: snapshot\ndata: {data}\n\n".encode())
                    except queue.Empty:
                        with hub.lock:
                            beat = json.dumps({"generated_at": hub.snap["generated_at"] if hub.snap else None,
                                               "server_time": time.strftime("%Y-%m-%dT%H:%M:%S")})
                        self.wfile.write(f"event: beat\ndata: {beat}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                hub.clients.discard(q)

    return H


def info_file(cfg):
    return common.state_path(cfg, "server.json")


def running_url(cfg):
    """URL of a live server, else None."""
    try:
        info = json.loads(info_file(cfg).read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/whoami", headers={"Host": f"127.0.0.1:{info['port']}"})
        with urllib.request.urlopen(req, timeout=2) as r:
            me = json.loads(r.read().decode("utf-8"))
        if me.get("app") != "WhyNotCC" or me.get("pid") != info.get("pid"):
            return None  # something else holds the port: never hand it the key
        return f"http://127.0.0.1:{info['port']}/?t={info['token']}"
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def main():
    cfg = common.load_config()
    url = running_url(cfg)
    if "--url" in sys.argv:
        print(url or "")
        return 0 if url else 1
    if url:
        print(f"Already running: {url}")
        return 0
    host, port = cfg["server"]["host"], int(cfg["server"]["port"])
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("server.host must stay 127.0.0.1 (this PC only)")
    try:  # keep the key across restarts, so an open page and its cookie keep working
        token = json.loads(info_file(cfg).read_text(encoding="utf-8"))["token"]
        assert len(token) >= 24
    except (OSError, ValueError, KeyError, AssertionError):
        token = secrets.token_urlsafe(24)
    hub = Hub(cfg)
    srv = http.server.ThreadingHTTPServer((host, port), make_handler(hub, token, port))
    srv.daemon_threads = True
    tmp = str(info_file(cfg)) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": token, "pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    os.replace(tmp, info_file(cfg))
    hub.note(f"server started on {host}:{port} (pid {os.getpid()})")
    threading.Thread(target=hub.run, daemon=True).start()
    print(f"WhyNot Control Center: http://127.0.0.1:{port}/?t={token}", flush=True)
    try:
        srv.serve_forever()
    finally:
        hub.note("server stopped")
    return 0


if __name__ == "__main__":
    if sys.stdout is None:  # pythonw
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    sys.exit(main())
