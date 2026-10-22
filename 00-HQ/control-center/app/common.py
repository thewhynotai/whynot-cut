"""Paths and settings shared by the control center. Reuses the 00-HQ tools (hq_status, agency_live) instead of
copying their parsers."""
import json, os, sys
from pathlib import Path

CC = Path(__file__).resolve().parent.parent          # 00-HQ\control-center
HQ = CC.parent                                        # 00-HQ
TOOLS = HQ / "tools"
WEB = CC / "web"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

CONFIG_FILE = Path(os.environ.get("WNC_CC_CONFIG") or CC / "config.json")


def load_config(path=None):
    with open(path or CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["state_dir"] = os.environ.get("WNC_CC_STATE") or cfg["state_dir"]
    return cfg


def state_path(cfg, *parts):
    p = Path(cfg["state_dir"], *parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def account(cfg, acct_id):
    for a in cfg["accounts"]:
        if a["id"] == acct_id:
            return a
    raise KeyError(acct_id)
