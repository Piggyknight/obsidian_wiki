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
from obsidian_wiki.config import DEFAULT_CONFIG, load_config, save_config
from obsidian_wiki.converter import convert_document
from obsidian_wiki.state import HashRegistry

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


def _find_vault_dir(override: Path | None = None) -> Path | None:
    """Find the Obsidian vault root."""
    if override is not None:
        if (override / ".obsidian_wiki").is_dir() or (override / "index.md").exists():
            return override
        return None
    # Walk up from cwd
    current = Path.cwd().resolve()
    while True:
        if (current / ".obsidian_wiki").is_dir() or (current / "index.md").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _setup_llm_key(vault_dir: Path | None = None) -> None:
    """Set LiteLLM API key from LLM_API_KEY env var."""
    if vault_dir is not None:
        env_file = vault_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)

    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        has_key = any(os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"))
        if not has_key:
            click.echo("Warning: No LLM API key found. Set LLM_API_KEY in your environment or .env file.")
    else:
        litellm.api_key = api_key
        for env_var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            if not os.environ.get(env_var):
                os.environ[env_var] = api_key


def add_single_file(file_path: Path, vault_dir: Path) -> None:
    """Convert, index, and compile a single document into the vault."""
    logger = logging.getLogger(__name__)
    state_dir = vault_dir / ".obsidian_wiki"
    state_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(state_dir / "config.yaml")
    _setup_llm_key(vault_dir)
    model: str = config.get("model", DEFAULT_CONFIG["model"])
    language: str = config.get("language", DEFAULT_CONFIG["language"])
    registry = HashRegistry(state_dir / "hashes.json")

    click.echo(f"Adding: {file_path.name}")
    try:
        result = convert_document(file_path, vault_dir, config)
    except Exception as exc:
        click.echo(f"  [ERROR] Conversion failed: {exc}")
        logger.debug("Conversion traceback:", exc_info=True)
        return

    if result.skipped:
        click.echo(f"  [SKIP] Already in knowledge base: {file_path.name}")
        return

    doc_name = file_path.stem

    if result.is_long_doc:
        click.echo(f"  Long document detected — indexing with PageIndex...")
        try:
            from obsidian_wiki.indexer import index_long_document
            index_result = index_long_document(result.raw_path, vault_dir)
        except Exception as exc:
            click.echo(f"  [ERROR] Indexing failed: {exc}")
            logger.debug("Indexing traceback:", exc_info=True)
            return

        summary_path = vault_dir / "summaries" / f"{doc_name}.md"
        click.echo(f"  Compiling long doc (doc_id={index_result.doc_id})...")
        for attempt in range(2):
            try:
                asyncio.run(compile_long_doc(
                    doc_name, summary_path, index_result.doc_id, vault_dir, model,
                    doc_description=index_result.description, language=language,
                ))
                break
            except Exception as exc:
                if attempt == 0:
                    click.echo(f"  Retrying compilation in 2s...")
                    time.sleep(2)
                else:
                    click.echo(f"  [ERROR] Compilation failed: {exc}")
                    logger.debug("Compilation traceback:", exc_info=True)
                    return
    else:
        click.echo(f"  Compiling short doc...")
        for attempt in range(2):
            try:
                asyncio.run(compile_short_doc(
                    doc_name, result.source_path, vault_dir, model, language=language,
                ))
                break
            except Exception as exc:
                if attempt == 0:
                    click.echo(f"  Retrying compilation in 2s...")
                    time.sleep(2)
                else:
                    click.echo(f"  [ERROR] Compilation failed: {exc}")
                    logger.debug("Compilation traceback:", exc_info=True)
                    return

    # Register hash after successful compilation
    if result.file_hash:
        doc_type = "long_pdf" if result.is_long_doc else file_path.suffix.lstrip(".")
        registry.add(result.file_hash, {"name": file_path.name, "type": doc_type})

    click.echo(f"  [OK] {file_path.name} added to knowledge base.")


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
        ctx.obj["vault_override"] = Path(vault_override)
    else:
        env_vault = os.environ.get("OBSIDIAN_WIKI_VAULT")
        ctx.obj["vault_override"] = Path(env_vault).resolve() if env_vault else None


@cli.command()
@click.argument("path", default=".")
def init(path):
    """Initialize .obsidian_wiki state in an existing Obsidian vault."""
    target = Path(path).resolve()
    if not (target / "index.md").exists():
        click.echo(f"Warning: {target} doesn't look like an Obsidian vault (no index.md).")
        click.echo("Creating state directory anyway...")

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

    state_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "model": model,
        "language": DEFAULT_CONFIG["language"],
        "pageindex_threshold": DEFAULT_CONFIG["pageindex_threshold"],
    }
    save_config(state_dir / "config.yaml", config)
    (state_dir / "hashes.json").write_text(json.dumps({}), encoding="utf-8")

    if api_key:
        env_path = target / ".env"
        if env_path.exists():
            click.echo(".env already exists, skipping.")
        else:
            env_path.write_text(f"LLM_API_KEY={api_key}\n", encoding="utf-8")
            os.chmod(env_path, 0o600)
            click.echo("Saved LLM API key to .env.")

    click.echo(f"Initialized in {target}")


@cli.command()
@click.argument("path")
@click.pass_context
def add(ctx, path):
    """Add a document or directory of documents to the vault."""
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found. Run `obsidian-wiki init` first, or set OBSIDIAN_WIKI_VAULT.")
        return

    target = Path(path)
    if not target.exists():
        click.echo(f"Path does not exist: {path}")
        return

    if target.is_dir():
        files = sorted(f for f in target.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not files:
            click.echo(f"No supported files found in {path}.")
            return
        total = len(files)
        click.echo(f"Found {total} supported file(s) in {path}.")
        for i, f in enumerate(files, 1):
            click.echo(f"\n[{i}/{total}] ", nl=False)
            add_single_file(f, vault_dir)
    else:
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            click.echo(f"Unsupported file type: {target.suffix}.")
            return
        add_single_file(target, vault_dir)


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
        click.echo("Vault not initialized. Run `obsidian-wiki init` first.")
        return

    registry = HashRegistry(state_dir / "hashes.json")
    entries = registry.all_entries()

    if not entries:
        click.echo("No documents indexed yet.")
        return

    click.echo(f"Known documents in {vault_dir}:\n")
    for h, meta in entries.items():
        doc_type = _display_type(meta.get("type", "?"))
        click.echo(f"  [{doc_type}] {meta.get('name', '?')}")
    click.echo(f"\nTotal: {len(entries)} document(s)")


@cli.command()
@click.argument("question")
@click.option("--save", is_flag=True, default=False, help="Save the answer to explorations/.")
@click.pass_context
def query(ctx, question, save):
    """Query the knowledge base using Obsidian search (not LLM)."""
    vault_dir = _find_vault_dir(ctx.obj.get("vault_override"))
    if vault_dir is None:
        click.echo("No vault found.")
        return

    import subprocess
    result = subprocess.run(
        ["obsidian", "search", f"query={question}", "limit=20"],
        capture_output=True, text=True,
        env={**os.environ, "OBSIDIAN_WIKI_VAULT": str(vault_dir)},
    )
    click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)


if __name__ == "__main__":
    cli()
