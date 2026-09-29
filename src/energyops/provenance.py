"""Checksums and source identity."""

import hashlib
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: str | Path) -> dict[str, str | int]:
    path = Path(path)
    return {"filename": path.name, "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path)}
