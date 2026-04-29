"""Obsidian Wiki CLI — build an Obsidian knowledge base from documents."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import click
import litellm
from dotenv import load_dotenv

from obsidian_wiki.compiler import compile_long_doc, compile_short_doc
from obsidian_wiki.config import DEFAULT_CONFIG, VaultLayout, load_config, save_config
from obsidian_wiki.converter import convert_document
from obsidian_wiki.state import HashRegistry

# Silence import warnings
import warnings
warnings.filterwarnings("ignore")

load_dotenv()

# Suppress debug noise from litellm
litellm.suppress_debug_info = True
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

SUPPORTED_EXTENSIONS = {
    ".pdf", ".md", ".markdown", ".docx", ".pptx", ".xlsx",
    ".html", ".htm", ".txt", ".csv",
}

_TYPE_DISPLAY_MAP = {"long_pdf": "pageindex"}
_SHORT_DOC_TYPES = {"pdf", "docx", "md", "markdown", "html", "htm", "txt", "csv", "pptx", "xlsx"}


def _display_type(raw_type: str) -> str:
    if raw_type in _TYPE_DISPLAY_MAP:
        return _TYPE_DISPLAY_MAP[raw_type]
    if raw_type in _SHORT_DOC_TYPES:
        return "short"
    return raw_type


# ---------------------------------------------------------------------------
# Vault discovery
# ---------------------------------------------------------------------------

def _find_vault_dir(override: Path | None = None) -> Path | None:
    """Find the Obsidian vault root by walking up from cwd."""
    if override is not None:
        if (override / ".obsidian_wiki").is_dir() or (override / "index.md").exists():
            return override.resolve()
        return None
    current = Path.cwd().resolve()
    while True:
        if (current / ".obsidian_wiki").is_dir() or (current / "index.md").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------

def _setup_llm_key(vault_dir: Path | None = None) -> None:
    """Set LiteLLM API key from LLM_API_KEY env var."""
    if vault_dir is not None:
        env_file = vault_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)

    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        has_key = any(os.environ.get(k) for k in (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
            "MINIMAX_API_KEY", "ZHIPU_API_KEY",
        ))
        if not has_key:
            click.echo("Warning: No LLM API key found. Set LLM_API_KEY in your environment or .env file.")
    else:
        litellm.api_key = api_key
        # Map LLM_API_KEY to all supported provider env vars
        for env_var in (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
            "MINIMAX_API_KEY", "ZHIPU_API_KEY",
        ):
            if not os.environ.get(env_var):
                os.environ[env_var] = api_key


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process_single_file(file_path: Path, vault_layout: VaultLayout, config: dict, registry: HashRegistry) -> bool:
    """Process a single file. Returns True if processed (new or updated), False if skipped."""
    state_dir = vault_layout.vault_root / ".obsidian_wiki"
    model: str = config.get("model", DEFAULT_CONFIG["model"])
    language: str = config.get("language", DEFAULT_CONFIG["language"])

    click.echo(f"  Adding: {file_path.name}")
    try:
        result = convert_document(file_path, vault_layout, config)
    except Exception as exc:
        click.echo(f"    [ERROR] Conversion failed: {exc}")
        return False

    if result.skipped:
        click.echo(f"    [SKIP] Already in knowledge base: {file_path.name}")
        return False

    doc_name = file_path.stem

    if result.is_long_doc:
        click.echo(f"    Long document — indexing with PageIndex...")
        try:
            from obsidian_wiki.indexer import index_long_document
            index_result = index_long_document(result.raw_path, vault_layout, config)
        except Exception as exc:
            click.echo(f"    [ERROR] Indexing failed: {exc}")
            return False

        summary_path = vault_layout.summary_path(doc_name)
        click.echo(f"    Compiling (doc_id={index_result.doc_id})...")
        for attempt in range(2):
            try:
                asyncio.run(compile_long_doc(
                    doc_name, summary_path, index_result.doc_id, vault_layout, model,
                    doc_description=index_result.description, language=language,
                ))
                break
            except Exception as exc:
                if attempt == 0:
                    click.echo(f"    Retrying in 2s...")
                    time.sleep(2)
                else:
                    click.echo(f"    [ERROR] Compilation failed: {exc}")
                    return False
    else:
        click.echo(f"    Compiling short doc...")
        for attempt in range(2):
            try:
                asyncio.run(compile_short_doc(
                    doc_name, result.source_path, vault_layout, model, language=language,
                ))
                break
            except Exception as exc:
                if attempt == 0:
                    click.echo(f"    Retrying in 2s...")
                    time.sleep(2)
                else:
                    click.echo(f"    [ERROR] Compilation failed: {exc}")
                    return False

    # Register hash after successful compilation
    if result.file_hash:
        doc_type = "long_pdf" if result.is_long_doc else file_path.suffix.lstrip(".")
        registry.add(result.file_hash, {"name": file_path.name, "type": doc_type})

    click.echo(f"    [OK] {file_path.name} added.")
    return True


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose logging.")
@click.option("--vault", "vault_override", default=None, type=click.Path(exists=True, file_okay=False, resolve_path=True), help="Path to Obsidian vault root.")
@click.pass_context
def cli(ctx, verbose, vault_override):
    """Obsidian Wiki — build an Obsidian knowledge base from documents."""
    logging.basicConfig(
        format="%(name)s %(levelname)s: %(message)s",
        level=logging.WARNING,
    )
    if verbose:
        logging.getLogger("obsidian_wiki").setLevel(logging.DEBUG)
    ctx.ensure_object(dict)
    if vault_override:
        ctx.obj["vault_override"] = Path(vault_override).resolve()
    else:
        env_vault = os.environ.get("OBSIDIAN_WIKI_VAULT")
        ctx.obj["vault_override"] = Path(env_vault).resolve() if env_vault else None


@cli.command()
@click.argument("path", default=".")
def init(path):
    """Initialize .obsidian_wiki state in an existing Obsidian vault."""
    target = Path(path).resolve()

    state_dir = target / ".obsidian_wiki"
    if state_dir.exists():
        click.echo("Already initialized.")
        return

    model = click.prompt(
        f"Model (enter for default {DEFAULT_CONFIG['model']})",
        default=DEFAULT_CONFIG["model"],
        show_default=False,
    )
    api_key = click.prompt(
        "LLM API Key (saved to .env, enter to skip)",
        default="",
        hide_input=True,
        show_default=False,
    ).strip()

    vault_layout_name = click.prompt(
        "Vault root namespace (subdirectory under vault, enter for default 'wiki')",
        default="wiki",
        show_default=False,
    )
    sources_input = click.prompt(
        "Raw data source directories (comma-separated, absolute or relative to cwd)",
        default="",
        show_default=False,
    ).strip()

    config = {
        **DEFAULT_CONFIG,
        "vault": {
            "root": vault_layout_name,
            "sources": "sources",
            "summaries": "summaries",
            "concepts": "concepts",
            "index": "index",
        },
        "sources": [s.strip() for s in sources_input.split(",") if s.strip()],
    }

    state_dir.mkdir(parents=True, exist_ok=True)
    save_config(state_dir / "config.yaml", config)
    (state_dir / "hashes.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

    # Create vault layout dirs
    layout = VaultLayout(target, config)
    layout.ensure_dirs()

    if api_key:
        env_path = target / ".env"
        if env_path.exists():
            click.echo(".env already exists, skipping.")
        else:
            env_path.write_text(f"LLM_API_KEY={api_key}", encoding="utf-8")
            os.chmod(env_path, 0o600)
            click.echo("Saved LLM API key to .env.")

    click.echo(f"\nInitialized in {target}")
    click.echo(f"  Vault namespace: {vault_layout_name}/")
    click.echo(f"  Source dirs: {config['sources'] or '(none — add manually to config)'}")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without changes.")
@click.pass_context
def sync(ctx, dry_run):
    """Scan configured source directories and process all supported files.

    Reads the ``sources`` list from .obsidian_wiki/config.yaml and
    recursively scans each directory, processing all supported file types.
    Already-processed files (by hash) are skipped.
    """
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found. Run `obsidian-wiki init` first, or set OBSIDIAN_WIKI_VAULT.")
        return

    state_dir = vault_dir / ".obsidian_wiki"
    if not state_dir.exists():
        click.echo("Vault not initialized. Run `obsidian-wiki init` first.")
        return

    config = load_config(state_dir / "config.yaml")
    vault_layout = VaultLayout(vault_dir, config)
    registry = HashRegistry(state_dir / "hashes.json")
    _setup_llm_key(vault_dir)

    source_dirs: list[str] = config.get("sources", [])
    if not source_dirs:
        click.echo("No source directories configured. Add paths to .obsidian_wiki/config.yaml -> sources:")
        return

    # Collect all files
    all_files: list[Path] = []
    for src in source_dirs:
        src_path = Path(src).resolve()
        if not src_path.exists():
            click.echo(f"  [WARN] Source directory not found, skipping: {src_path}")
            continue
        files = sorted(f for f in src_path.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
        click.echo(f"  {src_path}: {len(files)} supported file(s)")
        all_files.extend(files)

    if not all_files:
        click.echo("No supported files found.")
        return

    click.echo(f"\nTotal: {len(all_files)} file(s) to process")

    if dry_run:
        click.echo("\n[Dry run — no files will be modified]")
        for f in all_files:
            h = HashRegistry.hash_file(f)
            status = "[SKIP]" if registry.is_known(h) else "[NEW ]"
            click.echo(f"  {status} {f}")
        return

    processed = 0
    skipped = 0
    for f in all_files:
        h = HashRegistry.hash_file(f)
        if registry.is_known(h):
            click.echo(f"  [SKIP] {f.name} (already processed)")
            skipped += 1
            continue
        click.echo(f"\nProcessing: {f}")
        ok = _process_single_file(f, vault_layout, config, registry)
        if ok:
            processed += 1
        else:
            skipped += 1

    click.echo(f"\nDone: {processed} processed, {skipped} skipped, {len(all_files)} total")


@cli.command()
@click.argument("path")
@click.pass_context
def add(ctx, path):
    """Add a single document (or directory) to the vault."""
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found. Run `obsidian-wiki init` first.")
        return

    state_dir = vault_dir / ".obsidian_wiki"
    config = load_config(state_dir / "config.yaml")
    vault_layout = VaultLayout(vault_dir, config)
    registry = HashRegistry(state_dir / "hashes.json")
    _setup_llm_key(vault_dir)

    target = Path(path)
    if not target.exists():
        click.echo(f"Path does not exist: {path}")
        return

    if target.is_dir():
        files = sorted(f for f in target.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not files:
            click.echo(f"No supported files found in {path}.")
            return
        click.echo(f"Found {len(files)} file(s) in {path}.")
        for f in files:
            click.echo(f"\n[{f}]")
            _process_single_file(f, vault_layout, config, registry)
    else:
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            click.echo(f"Unsupported file type: {target.suffix}.")
            return
        _process_single_file(target, vault_layout, config, registry)


@cli.command()
@click.pass_context
def status(ctx):
    """Show known documents in the vault."""
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found.")
        return

    state_dir = vault_dir / ".obsidian_wiki"
    if not state_dir.exists():
        click.echo("Vault not initialized.")
        return

    config = load_config(state_dir / "config.yaml")
    vault_layout = VaultLayout(vault_dir, config)
    registry = HashRegistry(state_dir / "hashes.json")
    entries = registry.all_entries()

    click.echo(f"Vault: {vault_dir}")
    click.echo(f"Namespace: {config['vault']['root']}/\n")

    if not entries:
        click.echo("No documents indexed yet.")
        return

    click.echo(f"Known documents ({len(entries)}):\n")
    for h, meta in sorted(entries.items(), key=lambda x: x[1].get("name", "")):
        doc_type = _display_type(meta.get("type", "?"))
        click.echo(f"  [{doc_type}] {meta.get('name', '?')}")

    click.echo(f"\nSource directories configured: {config.get('sources', [])}")


@cli.command()
@click.argument("question")
@click.option("--save", is_flag=True, default=False, help="Save results to explorations/.")
@click.pass_context
def query(ctx, question, save):
    """Query the knowledge base using Obsidian search."""
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found.")
        return

    import subprocess
    result = subprocess.run(
        ["obsidian", "search", f"query={question}", "limit=20"],
        capture_output=True, text=True,
    )
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)

    if save:
        click.echo("\n[Save not yet implemented — use Obsidian to bookmark results]")


if __name__ == "__main__":
    cli()
