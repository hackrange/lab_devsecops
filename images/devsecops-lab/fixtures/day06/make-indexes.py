#!/usr/bin/env python3
"""
Build two tiny local Python package indexes for the dependency confusion demo.

  ~/pyindex/private/simple/acme-utils/  -> acme_utils 1.0.0  (the company's real package)
  ~/pyindex/public/simple/acme-utils/   -> acme_utils 99.0.0 (an "attacker" upload)

Wheels are written by hand with zipfile (a wheel is just a zip with metadata),
so nothing is downloaded.  Serve each folder with python3 -m http.server.
Author: Tim Rice
"""
import base64, hashlib, zipfile
from pathlib import Path

ROOT = Path.home() / "pyindex"


def rec(name, data):
    h = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={h},{len(data)}"


def wheel(dest: Path, version: str, body: str):
    dist = f"acme_utils-{version}"
    files = {
        "acme_utils/__init__.py": body.encode(),
        f"{dist}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: acme-utils\nVersion: {version}\nSummary: ACME internal helpers\n".encode(),
        f"{dist}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: lab\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = "\n".join(rec(n, d) for n, d in files.items()) + f"\n{dist}.dist-info/RECORD,,\n"
    dest.mkdir(parents=True, exist_ok=True)
    whl = dest / f"{dist}-py3-none-any.whl"
    with zipfile.ZipFile(whl, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
        z.writestr(f"{dist}.dist-info/RECORD", record)
    digest = hashlib.sha256(whl.read_bytes()).hexdigest()
    (dest / "index.html").write_text(
        f'<!DOCTYPE html><html><body><a href="{whl.name}#sha256={digest}">{whl.name}</a></body></html>\n')
    (dest.parent / "index.html").write_text('<!DOCTYPE html><html><body><a href="acme-utils/">acme-utils</a></body></html>\n')
    print(f"  {whl.relative_to(Path.home())}  sha256={digest[:16]}...")


wheel(ROOT / "private/simple/acme-utils", "1.0.0",
      'VERSION = "1.0.0"\ndef hello():\n    return "acme-utils 1.0.0: the real internal package"\n')
wheel(ROOT / "public/simple/acme-utils", "99.0.0",
      'VERSION = "99.0.0"\ndef hello():\n    return "acme-utils 99.0.0: ATTACKER CODE WOULD RUN HERE"\n'
      'print("[acme-utils 99.0.0] imported: this is the attacker\'s package, not yours")\n')
print("indexes ready under ~/pyindex")
