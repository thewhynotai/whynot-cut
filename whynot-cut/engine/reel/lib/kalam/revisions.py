# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Kalam: the model sources and the ONE table of the revision each is pinned to.

setup_models downloads every model at the revision recorded in docs/legal/third-party-licences.md (rows M4, M5, M7, M8, M9:
the table gives 8-hex prefixes, resolved to the full commit through the Hugging Face API). A download pinned to a commit
leaves a snapshot folder named by that commit and NO reference called "main" in the Hugging Face cache, so a lookup by repo
name alone (`snapshot_download(repo, local_files_only=True)`, `from_pretrained(repo)`) finds nothing. Every runtime lookup
therefore goes through `snapshot()` here, with the same pinned revision (Task 11 re-review N1). Nothing writes a reference
file by hand; the cache stays exactly as the real client made it.
"""
from __future__ import annotations

from .. import align_w2v as _align_w2v

ALIGNER_REPO, ALIGNER_REV = _align_w2v.MMS_REPO, _align_w2v.MMS_REV     # one place for the aligner (owner decision G8: MMS stays in
#                                                                      the 3.0 trial edition; the commercial edition replaces it)
REVISIONS = {
    "oddadmix/whisper-large-v3-turbo-arabic-dialectal": "cb15abb9792c4812f63de322eeb4e9ca00b79c49",    # M7
    "openai/whisper-large-v3-turbo": "41f01f3fe87f28c78e2fbf8b568835947dd65ed9",                       # M5
    "istupakov/parakeet-tdt-0.6b-v2-onnx": "0bbb45a3365852604aef28b538a8f066f4ccaa85",                 # M9
    ALIGNER_REPO: ALIGNER_REV,                                                                         # M8
    "mlx-community/whisper-large-v3-turbo": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",                # M4
    "mlx-community/parakeet-tdt-0.6b-v2": "8ae155301e23d820d82aa60d24817c900e69e487",                  # M9
}
LICENCES = {
    "oddadmix/whisper-large-v3-turbo-arabic-dialectal": "Apache-2.0",
    "openai/whisper-large-v3-turbo": "MIT",
    "istupakov/parakeet-tdt-0.6b-v2-onnx": "CC-BY-4.0 (attribution required)",
    ALIGNER_REPO: "CC-BY-NC-4.0 (non-commercial: 3.0 trial edition only)",
    "mlx-community/whisper-large-v3-turbo": "MIT (inherited)",
    "mlx-community/parakeet-tdt-0.6b-v2": "CC-BY-4.0 (inherited)",
}


def pinned(repo: str) -> str:
    """the pinned commit of `repo`; ValueError for a repo that has none (never fetched from its moving head)"""
    try:
        return REVISIONS[repo]
    except KeyError:
        raise ValueError("no pinned revision for %s: add it to lib/kalam/revisions.py (and the licence table) first" % repo) from None


def snapshot(repo: str, local_only: bool = False) -> str:
    """the local folder of the PINNED revision of `repo` (huggingface_hub.snapshot_download with that revision): the cache
    when it is there, otherwise downloaded at that commit unless `local_only` (then LocalEntryNotFoundError)"""
    from huggingface_hub import snapshot_download
    return snapshot_download(repo, revision=pinned(repo), local_files_only=local_only)
