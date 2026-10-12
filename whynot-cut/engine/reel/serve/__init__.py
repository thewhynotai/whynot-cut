"""`reel serve`: the local engine daemon the Premiere UXP panel talks to over WebSocket (3.0 Phase 6).

ws.py is the stdlib HTTP/1.1 + RFC 6455 transport (127.0.0.1 only); security.py holds the token, Host/Origin checks
and the audit log; the app and router sit on top of both.
"""
