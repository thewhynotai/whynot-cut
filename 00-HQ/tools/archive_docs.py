"""Move superseded planning documents into _archive/ with a manifest (copy, verify sha256, then remove the original).

Plain files only: refuses directories, links and reparse points. Dry run by default.
  python -X utf8 archive_docs.py            # dry run: prints what would move
  python -X utf8 archive_docs.py --apply    # move + append to 00-HQ/archive-manifest.jsonl
  python -X utf8 archive_docs.py --undo     # move every file of this batch back (verifies sha256)
"""
import datetime, hashlib, json, os, shutil, stat, sys

EP = os.environ.get("WNC_EP") or r"D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin"  # WNC_EP: mirror for the self-test
ARCH = os.path.join(EP, "_archive", "plans-2026-10")
MANIFEST = os.path.join(EP, "00-HQ", "archive-manifest.jsonl")
BATCH = os.environ.get("WNC_ARCHIVE_BATCH") or "2026-10-20-b1"  # which batch below to dry-run / apply / undo
SPEC = "WhyNotCut/docs/superpowers/specs/2026-10-18-v1-premiere-panel-design.md"
ROADMAP = "WhyNotCut/docs/superpowers/plans/2026-10-18-master-roadmap-v1.md"
B1 = [  # (relative path, classification, replacement, reason)
    ("V1-SCOPE-AR.md", "REFERENCE_ONLY", SPEC, "Superseded by the approved V1 spec (DOC-MAP 'Superseded'); spec cites it as a source"),
    ("NEW-PLAN-BRIEF-AR.md", "REFERENCE_ONLY", SPEC, "Owner answers folded into the V1 spec; §4 duplicates SAVED-LATER §4 (DOC-MAP #15)"),
    ("WhyNot-Cut-3.1-Plan/WHYNOT-CUT-3.1-PLAN.md", "ARCHIVE_READY", ROADMAP, "'3.1' is no longer used: V1 + Stage 11+ (DOC-MAP #8)"),
    ("PROJECT-PLAN-AR.md", "ARCHIVE_READY", "PROJECT_PLAN_AR.md", "Owner plan body from 10-17; replaced by the charter dashboard PROJECT_PLAN_AR.md"),
    ("API-LANES-PLAN.md", "ARCHIVE_READY", "00-HQ/BUDGET-API.md", "5-lane plan of 10-17; replaced by BUDGET-API.md + roles/API-LANES.md (DOC-MAP)"),
    ("WhyNot-Cut-3.0-Addendum/ADDENDUM-K-adopted-ideas.md.bak-kt8", "DUPLICATE_VERIFIED", "WhyNot-Cut-3.0-Addendum/ADDENDUM-K-adopted-ideas.md", "Pre-kt8 backup copy of the live addendum"),
    ("WhyNot-Cut-3.0-Addendum/ADDENDUM-M-owner-requests-2026-10-16.md.bak-kt8", "DUPLICATE_VERIFIED", "WhyNot-Cut-3.0-Addendum/ADDENDUM-M-owner-requests-2026-10-16.md", "Pre-kt8 backup copy of the live addendum"),
    ("00-HQ/MASTER-PLAN-AR.md", "ARCHIVE_READY", "PROJECT_PLAN_AR.md", "Owner plan v2 of 10-19 00:46 (design, approved); live view moved to PROJECT_PLAN_AR.md"),
]
B2 = [  # AI-infra restart Phase 5 (2026-10-22): only files no live code, role or enabled routine reads
    ("PARKED-SESSIONS.md", "HISTORICAL", "00-HQ/AUTOMATION_RUNBOOK.md + the app's Archived sessions list", "List of chats archived 10-18; all came back or ended since"),
    ("API-PAUSE-AR.md", "HISTORICAL", "00-HQ/BUDGET-API.md", "API pause record of 10-18; the API state lives in BUDGET-API.md (HOLD); only the retired lane-watch routine named it"),
]
BATCHES = {"2026-10-20-b1": B1, "2026-10-22-b2": B2}
if BATCH not in BATCHES:
    raise SystemExit(f"unknown WNC_ARCHIVE_BATCH {BATCH!r}; valid: {', '.join(BATCHES)}")
ITEMS = BATCHES[BATCH]


def is_link(p):
    st = os.lstat(p)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def move(src, dst, expect=None):
    if not os.path.isfile(src) or is_link(src):
        raise SystemExit(f"not a plain file: {src}")
    if os.path.exists(dst):
        raise SystemExit(f"target exists: {dst}")
    digest = sha(src)
    if expect and digest != expect:
        raise SystemExit(f"sha256 mismatch: {src}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if sha(dst) != digest:
        os.remove(dst)
        raise SystemExit(f"copy verify failed: {src}")
    os.remove(src)
    return digest


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    if mode == "--undo":
        rows = [json.loads(l) for l in open(MANIFEST, encoding="utf-8") if l.strip()]
        for r in rows:
            if r["batch"] == BATCH and r["action"] == "archived":
                move(os.path.join(EP, r["new_path"]), os.path.join(EP, r["original_path"]), r["sha256"])
                print("restored", r["original_path"])
        return
    for rel, *_ in ITEMS:  # preflight: all or nothing
        src, dst = os.path.join(EP, rel), os.path.join(ARCH, rel)
        if not os.path.isfile(src) or is_link(src) or os.path.exists(dst):
            raise SystemExit(f"preflight failed, nothing moved: {rel}")
    for rel, cls, repl, why in ITEMS:
        src = os.path.join(EP, rel)
        dst = os.path.join(ARCH, rel)
        if mode != "--apply":
            print(f"would move {rel} -> {os.path.relpath(dst, EP)} [{cls}]")
            continue
        digest = move(src, dst)
        row = {"batch": BATCH, "action": "archived", "original_path": rel.replace("\\", "/"),
               "new_path": os.path.relpath(dst, EP).replace("\\", "/"), "classification": cls,
               "replacement": repl, "reason": why, "sha256": digest, "at": now}
        with open(MANIFEST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("archived", rel)
    old = os.path.join(EP, "WhyNot-Cut-3.1-Plan")
    if mode == "--apply" and os.path.isdir(old) and not os.listdir(old) and not is_link(old):
        os.rmdir(old)
        print("removed empty folder WhyNot-Cut-3.1-Plan")


if __name__ == "__main__":
    main()
