"""Persistent object store for source files (Task2 RAG §6.4, §15).

Files are immutable: written once to a temp path, fsync'd, then atomically
renamed to content-addressed path. A snapshot is marked ready only after
the file is durable.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

ALLOWED_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/pdf",
    "application/xml",
    "application/vnd.openxmlformats",
    "application/msword",
    "application/zip",
)
MAX_OBJECT_BYTES = 50 * 1024 * 1024  # 50 MiB


class ObjectStoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StoredObject:
    storage_path: str
    content_hash: str
    size_bytes: int
    mime_type: str | None


class ObjectStore:
    """Content-addressed store under root. Path layout: ab/cd/<sha256>."""

    def __init__(self, root: str | Path, *, max_bytes: int = MAX_OBJECT_BYTES):
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, content_hash: str) -> Path:
        return self.root / content_hash[:2] / content_hash[2:4] / content_hash

    def hash_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def exists(self, content_hash: str) -> bool:
        return self._path_for(content_hash).is_file()

    def put_bytes(self, data: bytes, *, mime_type: str | None = None) -> StoredObject:
        if len(data) > self.max_bytes:
            raise ObjectStoreError("too_large", f"object {len(data)} > {self.max_bytes}")
        if mime_type and not _mime_allowed(mime_type):
            raise ObjectStoreError("bad_mime", f"mime not allowed: {mime_type}")
        content_hash = self.hash_bytes(data)
        dest = self._path_for(content_hash)
        if dest.is_file():
            return StoredObject(str(dest), content_hash, dest.stat().st_size, mime_type)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
            # best-effort directory durability
            dfd = os.open(str(dest.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError as exc:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise ObjectStoreError("write_failed", str(exc)) from exc
        return StoredObject(str(dest), content_hash, len(data), mime_type)

    def put_file(self, src: str | Path, *, mime_type: str | None = None) -> StoredObject:
        src = Path(src)
        size = src.stat().st_size
        if size > self.max_bytes:
            raise ObjectStoreError("too_large", f"file {size} > {self.max_bytes}")
        h = hashlib.sha256()
        with src.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        content_hash = h.hexdigest()
        dest = self._path_for(content_hash)
        if dest.is_file():
            return StoredObject(str(dest), content_hash, dest.stat().st_size, mime_type)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
                for block in iter(lambda: inp.read(1024 * 1024), b""):
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, dest)
        except OSError as exc:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise ObjectStoreError("write_failed", str(exc)) from exc
        return StoredObject(str(dest), content_hash, size, mime_type)

    def get_bytes(self, content_hash: str) -> bytes:
        path = self._path_for(content_hash)
        if not path.is_file():
            raise ObjectStoreError("not_found", f"no object {content_hash}")
        return path.read_bytes()

    def verify(self, content_hash: str) -> bool:
        path = self._path_for(content_hash)
        if not path.is_file():
            return False
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest() == content_hash

    def manifest(self) -> list[dict]:
        """Object list for backup (§15)."""
        out: list[dict] = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.startswith(".tmp-"):
                out.append({
                    "content_hash": p.name,
                    "size_bytes": p.stat().st_size,
                    "path": str(p.relative_to(self.root)),
                })
        return out

    def write_manifest(self, dest: str | Path) -> Path:
        dest = Path(dest)
        dest.write_text(json.dumps(self.manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
        return dest


def _mime_allowed(mime: str) -> bool:
    m = mime.split(";")[0].strip().lower()
    return any(m.startswith(p) or m == p for p in ALLOWED_MIME_PREFIXES)
