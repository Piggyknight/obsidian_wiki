"""Configuration management with hierarchical vault layout support."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "model": "gpt-5.4-mini",
    "language": "en",
    "pageindex_threshold": 20,
    # Vault layout — all paths relative to vault root
    "vault": {
        "root": "wiki",        # root node: all generated content lives under vault_root/wiki/
        "sources": "sources",  # converted document markdown
        "summaries": "summaries",  # per-doc summary pages
        "concepts": "concepts",    # LLM-generated concept pages
        "index": "index",          # index file (without .md)
    },
    # Raw data source directories to scan (absolute or relative to cwd)
    # Supports multiple sources; each source is recursively scanned
    "sources": [],
}


def load_config(config_path: Path) -> dict[str, Any]:
    """Load YAML config from config_path, merged with DEFAULT_CONFIG."""
    config = _deep_merge(dict(DEFAULT_CONFIG), _load_yaml(config_path))
    return config


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base (override wins on conflict)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def save_config(config_path: Path, config: dict[str, Any]) -> None:
    """Persist config dict to YAML."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, allow_unicode=True, sort_keys=True)


class VaultLayout:
    """Resolves vault-relative paths from config.

    All paths are computed relative to the vault root, using the
    configurable ``vault.root`` as the base namespace.
    """

    def __init__(self, vault_root: Path, config: dict[str, Any]) -> None:
        self.vault_root = vault_root.resolve()
        vc = config.get("vault", {})
        root_name = vc.get("root", "wiki")
        self.root = (self.vault_root / root_name).resolve()
        self.sources = self._rel(vc.get("sources", "sources"))
        self.summaries = self._rel(vc.get("summaries", "summaries"))
        self.concepts = self._rel(vc.get("concepts", "concepts"))
        self.index_name = vc.get("index", "index")

    def _rel(self, name: str) -> Path:
        """Path relative to vault root (not under root namespace)."""
        return (self.vault_root / name).resolve()

    @property
    def index(self) -> Path:
        return (self.vault_root / f"{self.index_name}.md").resolve()

    def source_md_path(self, doc_name: str) -> Path:
        return (self.sources / f"{doc_name}.md").resolve()

    def source_json_path(self, doc_name: str) -> Path:
        return (self.sources / f"{doc_name}.json").resolve()

    def summary_path(self, doc_name: str) -> Path:
        return (self.summaries / f"{doc_name}.md").resolve()

    def images_dir(self, doc_name: str) -> Path:
        return (self.sources / "images" / doc_name).resolve()

    def raw_dir(self) -> Path:
        return (self.vault_root / "raw").resolve()

    def ensure_dirs(self) -> None:
        """Create all layout directories."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.sources.mkdir(parents=True, exist_ok=True)
        self.summaries.mkdir(parents=True, exist_ok=True)
        self.concepts.mkdir(parents=True, exist_ok=True)
