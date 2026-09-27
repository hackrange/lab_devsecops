#!/usr/bin/env python3
"""
Simulate, safely and locally, how GitHub Actions runs one `run:` step.

GitHub expands every ${{ ... }} expression by plain text substitution BEFORE
the shell sees the script.  This tool does the same thing with a pull request
title you choose, prints the exact script the runner would hand to bash, and
then runs it with the same shell flags GitHub uses (bash --noprofile --norc
-eo pipefail) in a throwaway workspace.

The workspace imitates what actions/checkout leaves behind by default: a git
repository whose config holds the job token in an http extraheader (a FAKE
LAB_SECRET_ marker here, so nothing real can leak).

Usage:  simulate-step.py STEP.yml "pull request title"

Author: Tim Rice
"""
import json
import os
import re
import subprocess
import sys
import tempfile

EXPR = re.compile(r"\$\{\{\s*github\.event\.pull_request\.title\s*\}\}")
FAKE_HEADER = "AUTHORIZATION: basic LAB_SECRET_GITHUB_TOKEN_x-access-token_0001"


def expand(text: str, title: str) -> str:
    """GitHub's substitution: the value is pasted in as raw text, no quoting."""
    return EXPR.sub(lambda _m: title, text)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[-3])
        return 2
    step_file, title = sys.argv[1], sys.argv[2]
    step = json.loads(subprocess.run(["yq", "-o=json", ".", step_file],
                                     check=True, capture_output=True, text=True).stdout)
    script = expand(step["run"], title)
    env = dict(os.environ)
    for k, v in (step.get("env") or {}).items():
        env[k] = expand(str(v), title)          # expanded into DATA, not into code

    print(f"--- step: {step.get('name', '(unnamed)')}")
    for k in (step.get("env") or {}):
        print(f"--- env {k}={env[k]}")
    print("--- script the runner hands to bash:")
    print(script)
    print("--- output:")
    sys.stdout.flush()

    with tempfile.TemporaryDirectory(prefix="runner-workspace-") as ws:
        subprocess.run(["git", "init", "-q", ws], check=True)
        subprocess.run(["git", "-C", ws, "config", "http.https://github.com/.extraheader", FAKE_HEADER], check=True)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", dir=ws, delete=False) as f:
            f.write(script + "\n")
        rc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", f.name],
                            cwd=ws, env=env).returncode
    print(f"--- step exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
