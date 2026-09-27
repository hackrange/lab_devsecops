#!/usr/bin/env python3
"""
Day 9 fixture: assemble a tiny, harmless container image that "deleted" its
secrets, so you can prove that layers remember everything.

It writes an OCI image layout to ~/scratch/leaky-image (no container daemon
needed).  The layers are exactly what a real build of leaky.Dockerfile makes,
minus the base image, so the fixture stays a few kilobytes:

  layer 1  WORKDIR /app                 an empty /app directory
  layer 2  COPY app/ ./                 server.js, package.json, and .env
  layer 3  RUN ... > .npmrc             an .npmrc holding the build token
  layer 4  RUN rm -f .env .npmrc        whiteout markers that HIDE both files

The history entries use the same text BuildKit records, including the build
argument that leaks into every RUN line.  All secrets are fake LAB_SECRET_
markers.  Timestamps are fixed, so every student gets the same digests.

Author: Tim Rice
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

OUT = Path.home() / "scratch" / "leaky-image"
EPOCH = 1789689600  # 2026-09-18T00:00:00Z, fixed so the digests never change
CREATED = "2026-09-18T00:00:00Z"
TOKEN = "LAB_SECRET_d09_npm_token_not_real"

SERVER_JS = b"""import http from 'node:http';
http.createServer((req, res) => res.end('ok')).listen(3000, '0.0.0.0');
"""
PACKAGE_JSON = b"""{ "name": "leaky-demo", "version": "1.0.0", "type": "module" }
"""
DOT_ENV = b"""# local settings, copied into the image by COPY app/ ./
DB_HOST=db.internal.example
DB_PASSWORD=LAB_SECRET_d09_db_password_not_real
"""
NPMRC = f"//registry.npmjs.org/:_authToken={TOKEN}\n".encode()


def layer(entries: list[tuple[str, bytes | None]]) -> tuple[bytes, str, str]:
    """Build one gzipped layer.  entries: (path, bytes) for a file or
    (path/, None) for a directory.  Returns (blob, blob digest, diff_id)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path, data in entries:
            info = tarfile.TarInfo(path.rstrip("/"))
            info.mtime = EPOCH
            info.uid = info.gid = 0
            if data is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    diff_id = "sha256:" + hashlib.sha256(raw.getvalue()).hexdigest()
    blob = gzip.compress(raw.getvalue(), mtime=0)
    return blob, "sha256:" + hashlib.sha256(blob).hexdigest(), diff_id


def write_blob(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    (OUT / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
    (OUT / "blobs" / "sha256" / digest).write_bytes(data)
    return "sha256:" + digest


def main() -> None:
    layers = [
        layer([("app/", None)]),
        layer([("app/", None), ("app/server.js", SERVER_JS),
               ("app/package.json", PACKAGE_JSON), ("app/.env", DOT_ENV)]),
        layer([("app/", None), ("app/.npmrc", NPMRC)]),
        # A whiteout file ".wh.NAME" means "NAME was deleted in this layer".
        layer([("app/", None), ("app/.wh..env", b""), ("app/.wh..npmrc", b"")]),
    ]
    arg = f"|1 NPM_TOKEN={TOKEN} /bin/sh -c"
    history = [
        {"created": CREATED, "created_by": f"ARG NPM_TOKEN={TOKEN}",
         "comment": "buildkit.dockerfile.v0", "empty_layer": True},
        {"created": CREATED, "created_by": "WORKDIR /app", "comment": "buildkit.dockerfile.v0"},
        {"created": CREATED, "created_by": "COPY app/ ./ # buildkit", "comment": "buildkit.dockerfile.v0"},
        {"created": CREATED, "created_by": f'RUN {arg} echo "//registry.npmjs.org/:_authToken=${{NPM_TOKEN}}" > .npmrc && echo installed # buildkit',
         "comment": "buildkit.dockerfile.v0"},
        {"created": CREATED, "created_by": f"RUN {arg} rm -f .env .npmrc # buildkit",
         "comment": "buildkit.dockerfile.v0"},
        {"created": CREATED, "created_by": 'CMD ["node" "server.js"]',
         "comment": "buildkit.dockerfile.v0", "empty_layer": True},
    ]
    config = {
        "architecture": "amd64",
        "os": "linux",
        "created": CREATED,
        "config": {"WorkingDir": "/app", "Cmd": ["node", "server.js"],
                   "Env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]},
        "rootfs": {"type": "layers", "diff_ids": [d for _, _, d in layers]},
        "history": history,
    }
    cfg = json.dumps(config, separators=(",", ":")).encode()
    cfg_digest = write_blob(cfg)
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": cfg_digest, "size": len(cfg)},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": write_blob(blob), "size": len(blob)} for blob, _, _ in layers],
    }
    man = json.dumps(manifest, separators=(",", ":")).encode()
    man_digest = write_blob(man)
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{"mediaType": manifest["mediaType"], "digest": man_digest, "size": len(man),
                       "annotations": {"org.opencontainers.image.ref.name": "1.0"}}],
    }
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    (OUT / "oci-layout").write_text('{"imageLayoutVersion": "1.0.0"}')
    print(f"wrote an OCI image layout to {OUT}")
    print(f"image digest: {man_digest}")
    print("next: push it to a throwaway local registry with crane (see the lab)")


if __name__ == "__main__":
    main()
