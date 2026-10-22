import json, glob, os, sys, time, datetime as dt, collections
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 24
now = time.time(); cut = now - HOURS * 3600
titles = {}
for f in glob.glob(os.path.expandvars(r'%APPDATA%\Claude\claude-code-sessions\*\*\local_*.json')):
    try: d = json.load(open(f, encoding='utf-8'))
    except Exception: continue
    if d.get('cliSessionId'): titles[d['cliSessionId']] = ((d.get('title') or '')[:45], d.get('model'), d.get('effort'), d.get('scheduledTaskId'))
root = os.path.expanduser(r'~\.claude\projects')
agg = collections.defaultdict(lambda: collections.Counter())
first = {}
W = dict(input_tokens=1, cache_creation_input_tokens=1.25, cache_read_input_tokens=0.1, output_tokens=5)
for f in glob.glob(root + r'\*\*.jsonl') + glob.glob(root + r'\*\*\subagents\*.jsonl'):
    if os.path.getmtime(f) < cut: continue
    parts = f.split(os.sep)
    sid = parts[-3] if parts[-2] == 'subagents' else os.path.basename(f)[:-6]
    sub = parts[-2] == 'subagents'
    seen = set()
    for line in open(f, encoding='utf-8', errors='replace'):
        try: e = json.loads(line)
        except Exception: continue
        if sid not in first and e.get('type') == 'user' and not sub:
            c = (e.get('message') or {}).get('content')
            if isinstance(c, str): first[sid] = c[:60]
        m = e.get('message') or {}
        u = m.get('usage')
        ts = e.get('timestamp')
        if not u or not ts: continue
        t = dt.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
        if t < cut: continue
        mid = m.get('id')
        if mid in seen: continue
        seen.add(mid)
        w = sum(u.get(k, 0) * v for k, v in W.items())
        mult = 1 if 'opus' in (m.get('model') or '') else (0.6 if 'sonnet' in (m.get('model') or '') else 0.2)
        agg[sid]['w'] += w * mult
        agg[sid]['sub' if sub else 'main'] += w * mult
        agg[sid]['calls'] += 1
        agg[sid]['out'] += u.get('output_tokens', 0)
tot = sum(a['w'] for a in agg.values())
print(f"last {HOURS} h, weighted Opus-input-equivalent tokens, total {tot/1e6:.1f}M")
for sid, a in sorted(agg.items(), key=lambda x: -x[1]['w'])[:25]:
    t = titles.get(sid, ('', '', '', ''))
    name = t[0] or first.get(sid, '?')
    name = name.encode('ascii', 'replace').decode()
    print(f"{a['w']/tot*100:5.1f}%  {a['w']/1e6:6.2f}M  sub {a['sub']/max(a['w'],1)*100:3.0f}%  calls {a['calls']:5d}  {sid[:8]}  {t[1] or ''} {t[2] or ''} {t[3] or ''} | {name}")
