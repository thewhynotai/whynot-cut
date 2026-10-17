# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Shared setup for the parser fuzz tests (Addendum L §L4.4, Phase 4 Task 48 / L-T10).

Hypothesis is a dev tool (L-G37): it is NOT in the runtime locks. `tools/security/install_tools.py --fuzz` installs it,
hash-pinned, into `<tools home>/fuzz-py<major><minor>`, next to the engine runtime's Python version; this module finds it
there. Without it every fuzz test skips with that instruction (a skip is printed in the run summary, never silent).

Profiles (env WNC_FUZZ_PROFILE):
  unit (default)  fixed seed (derandomize), 60 examples per target: part of the normal suite, a few seconds each.
  long            10,000 examples for every target (a HEAVY waiver, fuzz(heavy=<bytes>), needs a 100 KB example and runs 1,500),
                  a fresh random seed each run, run only through heavy.sh at gates (tools/security/fuzz_long.py enforces the counts). A failing example is printed as a reproducible blob and must become an entry
                  in regressions.json (tests/test_fuzz_regressions.py replays it forever).
The property for every target: only our typed errors (or a returned error value) come out, nothing is written outside
the temp folder given to the target, and nothing runs longer than the target's time cap.
"""
import json
import os
import re
import sys
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parents[1]
ROOT = TESTS.parents[1]
ENGINE = ROOT / "whynot-cut" / "engine" / "reel"
INSTALL_HINT = "Hypothesis is not installed: python tools/security/install_tools.py --fuzz"


def _tools_home():
    env = os.environ.get("WNC_SEC_TOOLS")
    if env:
        return Path(env)
    import json
    v = json.loads((ROOT / "tools" / "security" / "versions.json").read_text(encoding="utf-8"))
    return Path(v["tools_home_default"])


def _find_hypothesis():
    try:
        import hypothesis  # noqa: F401
        return True
    except ImportError:
        pass
    target = _tools_home() / ("fuzz-py%d%d" % sys.version_info[:2])
    if target.is_dir():
        sys.path.append(str(target))
        try:
            import hypothesis  # noqa: F401,F811
            return True
        except ImportError:
            sys.path.remove(str(target))
    return False


AVAILABLE = _find_hypothesis()
PROFILE = os.environ.get("WNC_FUZZ_PROFILE", "unit")
LONG = PROFILE == "long"
EXAMPLES = int(os.environ.get("WNC_FUZZ_EXAMPLES", "10000" if LONG else "60"))
HEAVY_EXAMPLES = int(os.environ.get("WNC_FUZZ_HEAVY_EXAMPLES", "1500"))

requires_hypothesis = unittest.skipUnless(AVAILABLE, INSTALL_HINT)


def xfail_while_open(id_, open_ids):
    """The strict test of an open finding: `unittest.expectedFailure` while `id_` is in `open_ids`, unchanged after. When the
    owner applies the patch the test shows as an UNEXPECTED SUCCESS (a failed run): delete the id from the test file's OPEN
    dict and mark the finding fixed in regressions.json. A fuzz finding is never skipped."""
    return unittest.expectedFailure if id_ in open_ids else (lambda f: f)

LIGHT_REQUIRED = 10000          # the long profile's floor for every target (tools/security/fuzz_long.py enforces it)
HEAVY_REQUIRED = 1500           # ... for a target whose single example is HEAVY_MIN_BYTES or more (a recorded waiver)
HEAVY_MIN_BYTES = 100_000


def _plan(heavy, space, unit_examples, kw):
    """Validate the arguments of `fuzz()` and return (examples to run, examples required in the long profile)."""
    if "max_examples" in kw:
        raise ValueError("fuzz(): do not lower max_examples. Pass heavy=<bytes per example> (only honoured from %d bytes: HEAVY "
                         "waiver, %d examples in the long profile) or unit_examples=<n> (the unit profile only)"
                         % (HEAVY_MIN_BYTES, HEAVY_REQUIRED))
    if heavy is not None and heavy < HEAVY_MIN_BYTES:
        raise ValueError("fuzz(heavy=%d): a single example under %d bytes is not heavy; the target runs %d examples"
                         % (heavy, HEAVY_MIN_BYTES, LIGHT_REQUIRED))
    required = HEAVY_REQUIRED if heavy else LIGHT_REQUIRED
    if space is not None and space >= required:
        raise ValueError("fuzz(space=%d): the strategy space must be provably smaller than the %d required examples"
                         % (space, required))
    if LONG:
        return (min(EXAMPLES, HEAVY_EXAMPLES) if heavy else EXAMPLES), required
    return (min(unit_examples, EXAMPLES) if unit_examples else EXAMPLES), required


if AVAILABLE:
    from hypothesis import HealthCheck, given, settings, strategies as st  # noqa: F401

    COUNTS = {}
    SPACES = {}

    def fuzz(*, heavy=None, space=None, unit_examples=None, **kw):
        """settings() for one target: unit = derandomized fixed seed (`unit_examples` may lower the count, unit profile only);
        long = LIGHT_REQUIRED (10,000) random examples for every target. The ONE exception is `heavy=<bytes per example>`,
        honoured only from HEAVY_MIN_BYTES (100 KB): that target runs HEAVY_REQUIRED (1,500) and is listed as a waiver in the
        fuzz report with its size. `space=<n>` declares a strategy whose whole space has fewer than the required examples
        (Hypothesis stops at exhaustion). In the long profile each test prints what it really ran at exit
        (`FUZZ-COUNT <test> <n> cap <c> space <s> heavy <bytes>`); tools/security/fuzz_long.py fails the gate when a target
        ran less than it must."""
        n, required = _plan(heavy, space, unit_examples, kw)
        base = dict(max_examples=n, deadline=None, database=None, derandomize=not LONG,
                    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
                    print_blob=True)
        base.update(kw)

        def apply(test):
            out = settings(**base)(test)
            hyp = getattr(out, "hypothesis", None)
            if LONG and hyp is not None:
                inner = hyp.inner_test
                key = "%s.%s" % (inner.__module__, inner.__qualname__)
                SPACES[key] = (n, space, heavy)

                def counted(*a, **k):
                    COUNTS[key] = COUNTS.get(key, 0) + 1
                    return inner(*a, **k)
                hyp.inner_test = counted
            return out
        return apply

    if LONG:
        import atexit

        @atexit.register
        def _print_counts():
            for k in sorted(set(COUNTS) | set(SPACES)):      # a registered target that never ran (skipped) prints 0: the gate fails it
                cap, space, heavy = SPACES.get(k, (None, None, None))
                print("FUZZ-COUNT %s %d cap %s space %s heavy %s" % (k, COUNTS.get(k, 0), cap, space, heavy), file=sys.stderr)
else:
    st = given = settings = None

    def fuzz(*, heavy=None, space=None, unit_examples=None, **kw):
        _plan(heavy, space, unit_examples, kw)
        return lambda f: f


def decode_input(v):
    """A recorded input (tests/security/fuzz/regressions.json) -> the Python value to replay: {"base64": s} -> bytes,
    {"repeat": [[piece, count], ...]} -> the pieces repeated and joined, lists and objects decoded inside, the rest as is."""
    import base64
    if isinstance(v, dict) and set(v) == {"base64"}:
        return base64.b64decode(v["base64"])
    if isinstance(v, dict) and set(v) == {"repeat"}:
        return "".join(str(piece) * int(n) for piece, n in v["repeat"])
    if isinstance(v, dict):
        return {k: decode_input(x) for k, x in v.items()}
    if isinstance(v, list):
        return [decode_input(x) for x in v]
    return v


class Hang(AssertionError):
    pass


def within(seconds, fn, *args, **kw):
    """Run fn in a daemon thread; raise Hang if it takes longer than `seconds` (the property 'never hangs').
    A thread cannot interrupt code that holds the GIL (a backtracking regex), so a watchdog (faulthandler) also ends the
    whole run with a traceback if the call is still going `seconds + 20` s later: a true hang is a loud failure, never a
    stalled run."""
    import faulthandler
    box = {}

    def go():
        try:
            box["ok"] = fn(*args, **kw)
        except BaseException as e:  # noqa: BLE001: the caller classifies it
            box["err"] = e

    t = threading.Thread(target=go, daemon=True)
    faulthandler.dump_traceback_later(seconds + 20, exit=True)
    try:
        t.start()
        t.join(seconds)
    finally:
        faulthandler.cancel_dump_traceback_later()
    if t.is_alive():
        raise Hang("still running after %.1fs: %s" % (seconds, getattr(fn, "__name__", fn)))
    if "err" in box:
        raise box["err"]
    return box.get("ok")


def only_typed(fn, allowed, *args, seconds=10, **kw):
    """Call fn; return its value, or the allowed exception instance. Any other exception is the finding: it propagates."""
    try:
        return within(seconds, fn, *args, **kw)
    except allowed as e:
        return e


# Hostile text pieces shared by the strategies (Arabic, bidi controls, NUL, odd whitespace, lone surrogates, emoji).
HOSTILE_PIECES = [
    "", " ", "\0", "a\0b", "\ufeff", "\u202e", "\u202d", "\u2066", "\u2069", "\u200f", "\u200e", "\u061c",
    "مرحبا", "السلام عليكم", "نص عربي ‏مع‏ إنجليزي English", "\udc80", "\ud800", "😀", "\r\n", "\n", "\t", "\x1b[31m",
    "../", "..\\", "C:\\", "\\\\?\\", "CON", "NUL", "a:b", "x" * 5000, "%00", "%2e%2e%2f",
]


_NETWORK_PATH = re.compile(r"^[\\/]{2}(?![.?][\\/])|^[\\/]{2}[.?][\\/]UNC[\\/]", re.I)


def is_network_path(name):
    """A string Windows reads as a UNC path (two separators and a host, or the extended `UNC\\` form): opening it makes the
    machine look the host up on the LAN / DNS, so a fuzzer must never send one (device paths `\\\\.\\X` and `\\\\?\\X` are not)."""
    return bool(_NETWORK_PATH.match(name))


def path_oddities():
    """Windows and POSIX path strings that have broken file code before: traversal, device names, ADS, UNC, 8.3."""
    return ["..\\..\\x", "../../x", "C:\\x\\..\\y", "C:x", "x.", "x ", ".", "..", "", "CON", "con.txt", "NUL", "COM1", "LPT9.log",
            "CON:", "CON ", "NUL.", "CONIN$", "CONOUT$", "COM9:", "C:CON", "//./PhysicalDrive0", "//./CON", "\\\\?\\CON",
            "a:b", "a::$DATA", "\\\\?\\C:\\x", "\\\\.\\PhysicalDrive0", "PROGRA~1", "x\0y", "a/b\\c",
            "Client Folder\\Acme\\x", "x" * 300, "ملف عربي.srt", "\u202egnp.srt"]


if AVAILABLE:
    def hostile_text():
        return st.one_of(st.text(), st.sampled_from(HOSTILE_PIECES),
                         st.lists(st.sampled_from(HOSTILE_PIECES) | st.text(max_size=8), max_size=6).map("".join))

    def json_values(max_leaves=40):
        leaf = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=True, allow_infinity=True),
                         st.integers(min_value=-(2 ** 70), max_value=2 ** 70), hostile_text())
        return st.recursive(leaf, lambda c: st.one_of(st.lists(c, max_size=6),
                                                      st.dictionaries(hostile_text(), c, max_size=6)),
                            max_leaves=max_leaves)

    def deep_json(depth_max=1500):
        """Deeply nested lists/dicts: the recursion-limit class."""
        return st.integers(min_value=50, max_value=depth_max).flatmap(
            lambda n: st.sampled_from(["list", "dict"]).map(
                lambda k: _nest(n, k)))

    def _nest(n, kind):
        v = 0
        for _ in range(n):
            v = [v] if kind == "list" else {"a": v}
        return v


def deep_json_space(depth_max=1500):
    """How many distinct documents `deep_json(depth_max)` can make (depths 50..depth_max, list or dict). Hypothesis stops when a
    strategy is exhausted, so a target on it declares `fuzz(space=...)`."""
    return (depth_max - 49) * 2


def available_ram_mb():
    """Free physical memory in MB, or None when it cannot be read (then nothing is skipped)."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("tx", ctypes.c_ulonglong),
                            ("ax", ctypes.c_ulonglong), ("ex", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.ap // (1024 * 1024))
        pages, size = os.sysconf("SC_AVPHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        return int(pages * size // (1024 * 1024))
    except (OSError, ValueError, AttributeError, KeyError):
        return None


def requires_ram(mb):
    """Skip (with the reason printed) a test that allocates about `mb` MB when the machine has clearly less free."""
    free = available_ram_mb()
    return unittest.skipIf(free is not None and free < mb, "needs about %d MB free RAM, %s MB free" % (mb, free))


def schema_keys(node, depth=0):
    """Every property name used anywhere in a JSON schema (so a generator can build documents that reach its branches)."""
    out = set()
    if depth > 8 or not isinstance(node, (dict, list)):
        return out
    if isinstance(node, list):
        for x in node:
            out |= schema_keys(x, depth + 1)
        return out
    for k, v in node.items():
        if k == "properties" and isinstance(v, dict):
            out |= set(v)
        out |= schema_keys(v, depth + 1)
    return out


def schema_prop_enums(node, depth=0):
    """{property name: its enum / const values} for every property that has one, anywhere in a JSON schema."""
    out = {}
    if depth > 8 or not isinstance(node, (dict, list)):
        return out
    if isinstance(node, list):
        for x in node:
            for k, v in schema_prop_enums(x, depth + 1).items():
                out.setdefault(k, []).extend(v)
        return out
    props = node.get("properties")
    if isinstance(props, dict):
        for k, sub in props.items():
            if isinstance(sub, dict):
                vals = [x for x in (sub.get("enum") or []) if isinstance(x, (str, int, float, bool)) or x is None]
                if "const" in sub:
                    vals.append(sub["const"])
                if vals:
                    out.setdefault(k, []).extend(vals)
    for v in node.values():
        for k, vals in schema_prop_enums(v, depth + 1).items():
            out.setdefault(k, []).extend(vals)
    return {k: [x for _, x in sorted({(type(x), x) for x in v}, key=repr)] for k, v in out.items()}


def schema_literals(node, depth=0):
    """Every enum / const value used anywhere in a JSON schema, sorted by repr (so a generator can send the values the
    validators branch on, e.g. a step `type` or an `action` name, not only random JSON)."""
    out = []
    if depth > 8 or not isinstance(node, (dict, list)):
        return out
    if isinstance(node, list):
        for x in node:
            out += schema_literals(x, depth + 1)
        return out
    for k, v in node.items():
        if k == "enum" and isinstance(v, list):
            out += [x for x in v if isinstance(x, (str, int, float, bool)) or x is None]
        elif k == "const" and (isinstance(v, (str, int, float, bool)) or v is None):
            out.append(v)
        elif k == "type" and isinstance(v, str):
            out.append(v)
        out += schema_literals(v, depth + 1)
    seen, uniq = set(), []
    for x in out:
        if (type(x), x) not in seen:
            seen.add((type(x), x))
            uniq.append(x)
    return sorted(uniq, key=repr)


if AVAILABLE:
    def doc_from_keys(keys, value=None, extra=("x", ""), literals=(), prop_enums=None):
        """Dicts whose keys come from a schema (plus a few strangers) and whose values are hostile JSON or the schema's own
        enum / const values (`literals`; `prop_enums` maps a property to its own enum, so `type` gets a real type name and
        `items` a list in the same dict), one level of lists of such dicts included: they reach the schema's real branches
        (per-type, per-action) instead of failing at the first key."""
        keys = sorted(keys) or ["x"]
        value = value or json_values(max_leaves=12)
        if literals:  # the schema's own enum / const values, so per-type branches are reached
            value = st.one_of(value, st.sampled_from(list(literals)), st.sampled_from(list(literals)))
        prop_enums = prop_enums or {}

        def for_key(k):
            return st.one_of(value, st.sampled_from(prop_enums[k]), st.sampled_from(prop_enums[k])) if prop_enums.get(k) else value
        leaf = st.fixed_dictionaries({}, optional={k: for_key(k) for k in keys[:40]})
        return st.dictionaries(st.sampled_from(keys + list(extra)), st.one_of(value, st.lists(leaf, max_size=3), leaf),
                               max_size=min(len(keys) + 3, 12))


if AVAILABLE:
    def _resolve(ref, root):
        """A `$ref` ("#/a/b", or "<file>.schema.json#/a/b" inside the contract folder) -> (the node it names, the document
        its own "#/..." refs are relative to)."""
        file_part, _, ptr = ref.partition("#")
        node = root
        if file_part:
            if str(ENGINE) not in sys.path:
                sys.path.insert(0, str(ENGINE))
            from contract import validator
            node = root = validator.load(file_part)
        for part in [p for p in ptr.split("/") if p]:
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node, root

    def _string(node, hostile):
        """Strings that follow minLength / maxLength / pattern / format (valid ones always; hostile text only when asked)."""
        import datetime
        lo, hi = int(node.get("minLength", 0)), node.get("maxLength")
        hi = int(hi) if hi is not None else max(lo, 24)
        if node.get("format") == "date-time":
            return st.datetimes(min_value=datetime.datetime(2000, 1, 1), max_value=datetime.datetime(2100, 1, 1),
                                timezones=st.just(datetime.timezone.utc)).map(lambda d: d.isoformat().replace("+00:00", "Z"))
        pat = node.get("pattern")
        if pat:
            base = st.from_regex(pat.replace(r"\Z", ""), fullmatch=True)
            return base.filter(lambda s: lo <= len(s) <= hi and __import__("re").fullmatch(pat, s) is not None)
        if hostile:
            return st.text(min_size=lo, max_size=hi)
        return st.text(alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=chr(0)), min_size=lo, max_size=hi)

    def _number(node, integer):
        import math
        lo, hi = node.get("minimum"), node.get("maximum")
        if integer:
            lo = None if lo is None else math.ceil(lo)
            hi = None if hi is None else math.floor(hi)
            lo = lo if lo is not None else (hi - 10 ** 6 if hi is not None else -10 ** 6)
            hi = hi if hi is not None else lo + 2 * 10 ** 6
            return st.integers(lo, hi)
        lo = lo if lo is not None else (hi - 10 ** 6 if hi is not None else -10 ** 6)
        hi = hi if hi is not None else lo + 2 * 10 ** 6
        return st.floats(lo, hi, allow_nan=False, allow_infinity=False)

    def _overlay(base, branch):
        """`base` (an object schema) with an anyOf / oneOf branch that only adds `properties` / `required` merged in: a property
        whose schema is `false` is removed (the branch forbids it)."""
        props = dict(base.get("properties") or {})
        req = list(base.get("required") or [])
        for k, v in (branch.get("properties") or {}).items():
            if v is False:
                props.pop(k, None)
                req = [r for r in req if r != k]
            else:
                props[k] = {**props[k], **v} if isinstance(props.get(k), dict) and isinstance(v, dict) else v
        req += [r for r in branch.get("required") or [] if r not in req]
        out = dict(base, properties=props)
        if req:
            out["required"] = req
        return out

    def from_schema(schema, root=None, depth=10, hostile=True):
        """A strategy for documents that follow a JSON schema (types, enums, consts, $ref incl. other contract files, oneOf /
        anyOf, arrays with minItems / maxItems / uniqueItems, objects with the schema's own property names and
        additionalProperties, minimum / maximum, minLength / maxLength, pattern, format date-time).
        hostile=True (default): hostile JSON is mixed in at every node, so the validators' error branches are reached.
        hostile=False: valid-only mode, nothing hostile is ever mixed in: the documents are meant to PASS the schema (tests
        measure how many do) so the code behind the validator, not only its first error, is exercised.
        `depth` counts nesting of values; `$ref` hops have their own budget so a long chain of refs costs no depth."""
        root = root if root is not None else schema
        junk = json_values(max_leaves=6) if hostile else st.nothing()

        def build(node, d, rt, refs=30):
            if node is True or node == {}:
                return st.one_of(st.none(), st.booleans(), st.integers(-100, 100), st.text(max_size=8)) | junk
            if not isinstance(node, dict) or d <= 0 or refs <= 0:
                return junk
            if "$ref" in node:
                try:
                    sub, sub_root = _resolve(node["$ref"], rt)
                except (KeyError, TypeError, ValueError):
                    return junk
                return build(sub, d, sub_root, refs - 1)
            if "const" in node:
                return st.sampled_from([node["const"]])
            if isinstance(node.get("enum"), list) and node["enum"]:
                return st.one_of(st.sampled_from(node["enum"]), st.sampled_from(node["enum"]), junk)
            for combo in ("oneOf", "anyOf", "allOf"):
                if isinstance(node.get(combo), list) and node[combo]:
                    base = {k: v for k, v in node.items() if k != combo}
                    shaped = "type" in base or "properties" in base
                    alts = [build(_overlay(base, b) if shaped and isinstance(b, dict) and "type" not in b and "$ref" not in b else b,
                                  d - 1, rt, refs) for b in node[combo]]
                    return st.one_of(*alts, junk)
            t = node.get("type")
            kinds = t if isinstance(t, list) else [t] if t else (["object"] if "properties" in node else [])
            parts = []
            for k in kinds:
                if k == "object":
                    props = node.get("properties") or {}
                    built = {p: build(s, d - 1, rt, refs) for p, s in list(props.items())[:60]}
                    need = [p for p in (node.get("required") or []) if p in built]
                    if any(built[p].is_empty for p in need):
                        continue           # a required property cannot be built (depth / ref budget): no object of this shape
                    optional = {p: v for p, v in built.items() if p not in need and not v.is_empty}
                    extra_schema = node.get("additionalProperties")
                    strict = st.fixed_dictionaries({p: built[p] for p in need}, optional=optional)
                    if isinstance(extra_schema, dict) or (hostile and extra_schema is not False):
                        val = build(extra_schema, d - 1, rt, refs) if isinstance(extra_schema, dict) else json_values(max_leaves=3)
                        if not val.is_empty:
                            names = st.text(alphabet="abcdefxyz_-", min_size=1, max_size=6).filter(lambda n: n not in built)
                            strict = st.tuples(strict, st.dictionaries(names, val, max_size=3)).map(lambda ab: {**ab[1], **ab[0]})
                    parts.append(st.one_of(strict, strict, st.fixed_dictionaries({}, optional=optional)) if hostile else strict)
                elif k == "array":
                    items = node.get("items")
                    lo = int(node.get("minItems", 1 if hostile and items else 0))
                    hi = max(lo, min(int(node.get("maxItems", max(lo, 4))), max(lo, 5)))
                    inner = build(items, d - 1, rt, refs) if items is not None else json_values(max_leaves=3)
                    if inner.is_empty:
                        if lo == 0:
                            parts.append(st.just([]))
                        continue
                    uniq = {"unique_by": lambda x: json.dumps(x, sort_keys=True, default=repr)} if node.get("uniqueItems") else {}
                    parts.append(st.lists(inner, min_size=lo, max_size=hi, **uniq))
                elif k == "string":
                    parts.append(_string(node, hostile))
                elif k == "integer":
                    parts.append(_number(node, True))
                elif k == "number":
                    parts.append(_number(node, False) | _number(node, True))
                elif k == "boolean":
                    parts.append(st.booleans())
                elif k == "null":
                    parts.append(st.none())
            if not parts:
                return junk
            typed = st.one_of(*parts)
            return st.one_of(typed, typed, typed, junk) if hostile else typed
        return build(schema, depth, root)


if AVAILABLE:
    VALID_SHARE_MIN = 0.20       # a schema's valid-only generator must give at least this share of documents that validate
    VALID_SHARE_EXAMPLES = 40

    def valid_share(strategy, errors_of, examples=VALID_SHARE_EXAMPLES):
        """(valid, drawn, first error text) for `examples` derandomized draws of `strategy` (a valid-only generator):
        `errors_of(doc)` returns the validator's error list. The number is stable: same seed, same Hypothesis pin."""
        stats = {"valid": 0, "drawn": 0, "first": ""}

        @settings(max_examples=examples, database=None, derandomize=True, deadline=None,
                  suppress_health_check=list(HealthCheck))
        @given(strategy)
        def probe(doc):
            stats["drawn"] += 1
            errs = errors_of(doc)
            if not errs:
                stats["valid"] += 1
            elif not stats["first"]:
                stats["first"] = str(errs[0])[:160]
        probe()
        return stats["valid"], stats["drawn"], stats["first"]


_SCRATCH = []


def scratch_dir(prefix="wncfuzz-"):
    """A fresh directory under ONE per-process root (the long profile makes 100k+ examples: a mkdtemp each in the temp root,
    never removed, would fill it). The root is WNC_FUZZ_SCRATCH when tools/security/fuzz_long.py set it (that script removes
    it after the run, so nothing leaks when the watchdog ends the process with _exit and no atexit handler runs); otherwise
    a temp folder under the test sandbox that is also removed at exit."""
    import atexit
    import shutil
    import tempfile
    if not _SCRATCH:
        env = os.environ.get("WNC_FUZZ_SCRATCH")
        if env:
            Path(env).mkdir(parents=True, exist_ok=True)
            _SCRATCH.append(env)
        else:
            root = tempfile.mkdtemp(prefix="wncfuzz-root-", dir=os.environ.get("TMP"))
            _SCRATCH.append(root)
            atexit.register(shutil.rmtree, root, True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=_SCRATCH[0]))


if AVAILABLE:
    # Hypothesis keeps its constants / unicode caches under .hypothesis in the working directory even with database=None:
    # keep them in the per-process scratch root, so a run writes nothing into the repo tree.
    from hypothesis.configuration import set_hypothesis_home_dir
    set_hypothesis_home_dir(scratch_dir("wnchyp-"))
