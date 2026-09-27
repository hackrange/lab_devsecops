"""Where lab checks register themselves.

    from .registry import check

    @check("d01_repo")
    def repo(ctx):
        ...
        return True, "secure-build-lab is on the lab Git server with 2 commits."

A check returns (passed, detail).  The detail is shown to the student: on a
pass, what was found; on a fail, what is missing and how to put it right, in
plain words.

Author: Tim Rice
"""

from __future__ import annotations

from typing import Callable

CHECKS: dict[str, Callable] = {}


def check(name: str):
    def register(fn: Callable) -> Callable:
        if name in CHECKS:
            raise ValueError(f"check {name} is registered twice")
        CHECKS[name] = fn
        return fn
    return register
