"""Content-type recipes (config/defaults/recipes.json, profile-overridable): how a reel of a given type is paced,
framed, captioned, decorated, scored and written about. The engine applies the numbers; story-editor and
publish-writer follow the rest."""
from __future__ import annotations

import copy

from .common import load_config


def types() -> dict:
    return load_config("recipes.json").get("types", {})


def resolve(type_id: str) -> dict:
    """The recipe for one type (a copy, with its id), or {} for an unknown type."""
    r = types().get(type_id)
    return dict(copy.deepcopy(r), type=type_id) if r else {}
