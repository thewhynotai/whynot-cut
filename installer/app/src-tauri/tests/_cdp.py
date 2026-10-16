"""A minimal Chrome DevTools Protocol client (stdlib only) for the live app test: WebSocket framing, calls, events.

Only for the app this test started, on 127.0.0.1, through the WebView2 debug port that the test sets for that one
process (WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS). Nothing here is part of the product.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.request


class WS:
    def __init__(self, url: str, timeout: float = 20):
        assert url.startswith("ws://127.0.0.1:"), url
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        head, self.rest = buf.split(b"\r\n\r\n", 1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.id = 0
        self.events: list[dict] = []

    def close(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass

    def _exact(self, n: int) -> bytes:
        while len(self.rest) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("CDP socket closed")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def recv(self) -> dict:
        data = b""
        while True:
            b1, b2 = self._exact(2)
            fin, op, ln = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._exact(8))[0]
            payload = self._exact(ln)
            if op in (0, 1, 2):
                data += payload
                if fin:
                    return json.loads(data)

    def send(self, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(raw)
        hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                               bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                               bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(raw)))

    def call(self, method: str, **params) -> dict:
        self.id += 1
        me = self.id
        self.send({"id": me, "method": method, "params": params})
        while True:
            m = self.recv()
            if m.get("id") == me:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)

    def drain(self, seconds: float) -> None:
        """Collect events for a while (the socket timeout ends each wait)."""
        end = time.time() + seconds
        self.s.settimeout(0.2)
        try:
            while time.time() < end:
                try:
                    self.events.append(self.recv())
                except (socket.timeout, TimeoutError):
                    pass
        finally:
            self.s.settimeout(20)

    def eval(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            return {"exception": r["exceptionDetails"].get("exception", {}).get("description")}
        return r["result"].get("value")


def http_json(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as r:
        return json.load(r)


# invoke through Tauri's own path (the isolation frame), with a 5 s timeout so a hang is a result, not a stall
INVOKE = ("(async c=>{try{return {ok: await Promise.race([window.__TAURI_INTERNALS__.invoke(c, {}),"
          "new Promise((_,j)=>setTimeout(()=>j('TIMEOUT 5s'),5000))])}}catch(e){return {err: String(e)}}})")


def directives(policy: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for d in policy.split(";"):
        words = d.split()
        if words:
            out[words[0].lower()] = words[1:]
    return out
