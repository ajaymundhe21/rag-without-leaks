"""At login, ask the identity system which groups the person is in, and open the group tree once.
data/identity.json stands in for Okta or Entra ID in this demo."""
import json
from functools import lru_cache
from .config import IDENTITY_FILE


@lru_cache(maxsize=1)
def _data():
    return json.load(open(IDENTITY_FILE))


def flatten(groups: list[str]) -> list[str]:
    """engineering -> product -> all-staff becomes [all-staff, engineering, product]."""
    parents, seen, todo = _data()["groups"], set(), list(groups)
    while todo:
        g = todo.pop()
        if g not in seen:
            seen.add(g)
            todo.extend(parents.get(g, []))
    return sorted(seen)


def login(user_id: str) -> tuple[int, list[str]]:
    u = _data()["users"].get(user_id)
    if u is None:
        raise KeyError(user_id)
    return u["tenant"], flatten(u["groups"])
