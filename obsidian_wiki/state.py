"""State management — file hash registry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class HashRegistry:
    """Persistent registry mapping file SHA-256 hashes to metadata dicts."""

    def __init__(self, path: Path) -> None:
        self._path = path
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                self._data: dict[str, dict] = json.load(fh)
        else:
            self._data = {}

    def is_known(self, file_hash: str) -> bool:
        return file_hash in self._data

    def get(self, file_hash: str) -> dict | None:
        return self._data.get(file_hash)

    def all_entries(self) -> dict[str, dict]:
        return dict(self._data)

    def add(self, file_hash: str, metadata: dict) -> None:
        self._data[file_hash] = metadata
        self._persist()

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    @staticmethod
    def hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
