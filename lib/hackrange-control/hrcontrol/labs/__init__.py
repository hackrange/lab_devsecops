"""The Labs tab: every lab by day, what finishing it means, and grading.

Each lab's items are the lesson's own Evidence checklist.  An item is either:

- checked by the lab ("auto"): a check function looks at what the student
  actually made (a repository, a merged pull request, a green pipeline, a
  cluster object, a GitHub ruleset) and says passed or not yet, with a hint;
- confirmed by the student ("self"): something only they saw, such as an
  error message or a prediction.  They tick it.

A lab is complete when every automatic check passes and every self item is
ticked.  Results are kept on this machine only
(/var/lib/hackrange/labs-progress.json), and survive restarts and resets.

Author: Tim Rice
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

from .checks import CHECKS
from .context import Context

# One file per week of the course (labs-catalog/week1.json ...), read together.
CATALOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "labs-catalog")
PROGRESS = "/var/lib/hackrange/labs-progress.json"
GITHUB_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

_lock = threading.Lock()


def catalog() -> list[dict]:
    days: list[dict] = []
    for name in sorted(os.listdir(CATALOG_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(CATALOG_DIR, name)) as fh:
                days += json.load(fh)["days"]
    return sorted(days, key=lambda d: d["day"])


def _load() -> dict:
    try:
        with open(PROGRESS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"github_user": "", "days": {}}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(PROGRESS), mode=0o700, exist_ok=True)
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, PROGRESS)


def _day(num: int) -> dict | None:
    return next((d for d in catalog() if d["day"] == num), None)


def _summary(day: dict, rec: dict) -> dict:
    items = rec.get("items", {})
    auto = [i for i in day["items"] if i.get("check")]
    selfs = [i for i in day["items"] if not i.get("check")]
    auto_ok = sum(1 for i in auto if items.get(i["id"], {}).get("state") == "pass")
    self_ok = sum(1 for i in selfs if items.get(i["id"], {}).get("state") == "confirmed")
    complete = auto_ok == len(auto) and self_ok == len(selfs)
    return {"auto_total": len(auto), "auto_passed": auto_ok,
            "self_total": len(selfs), "self_confirmed": self_ok,
            "complete": complete, "checked_at": rec.get("checked_at", 0),
            "score": round(100 * (auto_ok + self_ok) / max(len(day["items"]), 1))}


def overview() -> dict:
    """The whole Labs tab: every day, its items, and where the student stands."""
    data = _load()
    days = []
    for d in catalog():
        rec = data["days"].get(str(d["day"]), {})
        items = []
        for it in d["items"]:
            r = rec.get("items", {}).get(it["id"], {})
            items.append({"id": it["id"], "text": it["text"], "kind": "auto" if it.get("check") else "self",
                          "github": bool(it.get("github")), "state": r.get("state", ""),
                          "detail": r.get("detail", "")})
        days.append({"day": d["day"], "week": d["week"], "title": d["title"], "items": items,
                     **_summary(d, rec)})
    return {"github_user": data.get("github_user", ""), "days": days}


def check(num: int) -> dict:
    """Grade one lab: run every automatic check against the student's work."""
    day = _day(num)
    if not day:
        return {"error": "no such lab"}
    with _lock:
        data = _load()
        ctx = Context(data.get("github_user", ""))
        rec = data["days"].setdefault(str(num), {"items": {}})
        for it in day["items"]:
            name = it.get("check")
            if not name:
                continue
            if it.get("github") and not ctx.github_user:
                rec["items"][it["id"]] = {"state": "fail", "detail": "Enter your GitHub username at the top of this page first."}
                continue
            fn = CHECKS.get(name)
            try:
                ok, detail = fn(ctx) if fn else (False, "This check is missing from the lab.")
            except Exception as exc:  # a broken check must never break the page
                ok, detail = False, f"The check could not run: {exc.__class__.__name__}"
            rec["items"][it["id"]] = {"state": "pass" if ok else "fail", "detail": detail}
        rec["checked_at"] = int(time.time())
        _save(data)
    return overview()


def confirm(num: int, item: str, value: bool) -> dict:
    """The student ticks (or unticks) something only they could have seen."""
    day = _day(num)
    it = next((i for i in (day or {}).get("items", []) if i["id"] == item), None)
    if not it or it.get("check"):
        return {"error": "that item is checked by the lab, not ticked"}
    with _lock:
        data = _load()
        rec = data["days"].setdefault(str(num), {"items": {}})
        if value:
            rec["items"][item] = {"state": "confirmed", "detail": ""}
        else:
            rec["items"].pop(item, None)
        _save(data)
    return overview()


def set_github_user(name: str) -> dict:
    name = name.strip().lstrip("@")
    if name and not GITHUB_USER_RE.match(name):
        return {"error": "That is not a GitHub username."}
    with _lock:
        data = _load()
        data["github_user"] = name
        _save(data)
    return overview()
