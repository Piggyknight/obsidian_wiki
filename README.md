# Obsidian Wiki

Build an Obsidian knowledge base from raw documents using an LLM-powered pipeline. Forked from [OpenKB](https://github.com/VectifyAI/OpenKB) — adapts its compilation workflow for Obsidian vaults.

## Overview

```
Raw Documents          obsidian-wiki               Obsidian Vault
──────────────         ─────────────               ─────────────
PDF, MD, DOCX  ──→  LLM Processing  ────→  summaries/*.md
        ──────                              concepts/*.md
                                          sources/*.md + images/
                                          index.md
```

**Pipeline per document:**
1. **Convert** — Extract text + images from PDF/DOCX/MD/etc.
2. **Index** — For long PDFs (≥20 pages): PageIndex extracts TOC + per-page content
3. **Summarize** — LLM generates a brief summary
4. **Concept mining** — LLM identifies cross-document concepts to create/update
5. **Index** — Auto-maintain `index.md` linking all summaries and concepts

---

## Quick Start

```bash
# Install
pip install -e ~/Documents/tools/obsidian_wiki

# Initialize (in your Obsidian vault root)
cd ~/Documents/obsidian_vault
obsidian-wiki init

# Add documents manually
obsidian-wiki add ./papers/attention.pdf
obsidian-wiki add ./notes/

# Or sync all configured source directories
obsidian-wiki sync

# Check status
obsidian-wiki status
```

---

## Configuration

After `obsidian-wiki init`, edit `.obsidian_wiki/config.yaml`:

```yaml
# LLM settings
model: minimax/MiniMax-M2.7
language: en

# PDF long-doc threshold (pages)
# PDFs with >= this many pages use PageIndex for structured indexing
pageindex_threshold: 20

# Vault layout — all paths relative to vault root
vault:
  root: wiki              # root namespace: vault_root/wiki/
  sources: sources        # converted document markdown
  summaries: summaries    # per-document summary pages
  concepts: concepts      # LLM-generated concept pages
  index: index            # index file (without .md)

# Source directories to scan (absolute or relative to cwd)
# Supports any number of dirs; each is recursively scanned
sources:
  - ~/Documents/research/papers
  - ~/Downloads/articles
  - ./my_notes
```

---

## Supported Models

Uses [LiteLLM](https://docs.litellm.ai/) — any model LiteLLM supports works out of the box. Just set the appropriate API key and use the model identifier as the `model` value in config.

| Provider | Model Identifier | API Key |
|----------|-----------------|---------|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `gpt-5.4-mini` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/claude-sonnet-4-6`, `anthropic/claude-3-5-sonnet-20241002` | `ANTHROPIC_API_KEY` |
| Gemini | `gemini/gemini-2.5-pro`, `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |
| MiniMax | `minimax/MiniMax-M2.7` | `MINIMAX_API_KEY` |
| Zhipu/GLM | `zhipu/glm-4-plus`, `zhipu/glm-4v` | `ZHIPU_API_KEY` |

> **Tip:** During `obsidian-wiki init`, if you provide your `LLM_API_KEY`, it will be automatically mapped to all provider key variables so any model can be used without extra configuration.

### Vault Layout

All generated content lives under `{vault.root}/` inside the Obsidian vault:

```
vault_root/
├── .obsidian_wiki/        # state (do not edit)
│   ├── config.yaml
│   └── hashes.json
├── .env                   # LLM_API_KEY (optional)
├── wiki/                  # ← vault.root
│   ├── index.md           # auto-maintained knowledge base index
│   ├── sources/           # converted markdown + extracted images
│   │   ├── *.md
│   │   ├── *.json         # long PDFs: per-page content
│   │   └── images/
│   │       └── {doc_name}/
│   ├── summaries/         # per-document summary pages
│   │   └── *.md
│   └── concepts/          # cross-document concept pages
│       └── *.md
├── raw/                   # original file copies
└── ... (your existing Obsidian notes)
```

---

## CLI Commands

```bash
obsidian-wiki --vault VAULT_DIR [command]

Commands:
  init              Initialize vault (creates .obsidian_wiki/)
  sync              Scan configured source dirs, process all files
  add PATH          Add a single file or directory
  status            Show indexed documents and source dirs
  query "keywords"  Search vault via Obsidian CLI
```

### `obsidian-wiki init`

Interactive initialization. Sets up `.obsidian_wiki/` and creates layout directories.

```
Model (enter for default minimax/MiniMax-M2.7): anthropic/claude-sonnet-4-6
Vault root namespace (enter for 'wiki'): wiki
Raw data source directories (comma-separated): ~/research/papers,./notes
```

### `obsidian-wiki sync`

Reads `sources` from config, recursively scans all directories, processes new files:

```bash
# See what would be done without changes
obsidian-wiki sync --dry-run

# Actually process
obsidian-wiki sync
```

Files are deduplicated by SHA-256 hash — re-running `sync` skips already-processed files.

### `obsidian-wiki add`

Add individual files or directories without changing the configured sources:

```bash
obsidian-wiki add ./new_paper.pdf
obsidian-wiki add ./some_notes/
```

### `obsidian-wiki status`

```
Vault: /home/kai/Documents/obsidian_vault
Namespace: wiki/

Known documents (4):

  [pageindex] attention_is_all_you_need.pdf
  [short]    llm_survey.md
  [short]    rllm_chapter3.pdf
  [pageindex] mixture_of_experts.pdf

Source directories configured:
  - ~/Documents/research/papers
  - ~/Downloads/articles
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OBSIDIAN_WIKI_VAULT` | Vault root path (alternative to `--vault`) |
| `LLM_API_KEY` | API key for LiteLLM (OpenAI, Anthropic, Gemini, MiniMax, GLM, etc.) |
| `MINIMAX_API_KEY` | MiniMax API key (auto-set from `LLM_API_KEY` during init) |
| `ZHIPU_API_KEY` | Zhipu/GLM API key (auto-set from `LLM_API_KEY` during init) |
| `PAGEINDEX_API_KEY` | Optional: use PageIndex cloud API instead of local |

Set `LLM_API_KEY` in your vault's `.env` file or export it in your shell.

---

## Supported File Types

| Type | Extension | Notes |
|------|----------|-------|
| PDF | `.pdf` | Short docs: text extracted via pymupdf. Long docs (≥threshold): PageIndex structured indexing |
| Markdown | `.md`, `.markdown` | Relative image links rewritten to `sources/images/` |
| Word | `.docx` | Via markitdown |
| Excel | `.xlsx` | Via markitdown |
| PowerPoint | `.pptx` | Via markitdown |
| HTML | `.html`, `.htm` | Via markitdown |
| Text | `.txt`, `.csv` | Plain text |

---

## Architecture

```
obsidian_wiki/
├── cli.py           # Click CLI: init, add, sync, status, query
├── config.py        # YAML config + VaultLayout path resolver
├── converter.py     # Document → markdown conversion
├── indexer.py       # PageIndex long-PDF indexing
├── compiler.py      # LLM pipeline: summary + concept generation
├── images.py        # PDF/markdown image extraction
├── state.py         # HashRegistry (dedup by SHA-256)
└── tree_renderer.py # PageIndex tree → markdown
```

**Key design decisions:**
- State stored in `.obsidian_wiki/` at vault root — not inside the namespace
- Deduplication by file hash — safe to re-run `sync` without reprocessing
- All vault paths resolved through `VaultLayout` — change `vault.root` in config to rename the namespace
- Query delegates to Obsidian CLI — no separate RAG/embedding step needed

---

## PageIndex (Long PDFs)

For PDFs with ≥ `pageindex_threshold` pages, the pipeline uses [PageIndex](https://github.com/niceprivate/pageindex):

1. PageIndex extracts TOC, per-section summaries, and page-level text
2. A structured summary page is generated from the TOC tree
3. Concept pages are derived from the document structure

Requires `PAGEINDEX_API_KEY` for cloud mode. Without it, falls back to local pymupdf for text extraction.

---

## Obsidian Integration

- Generated files use `[[wikilinks]]` for cross-referencing
- `index.md` is auto-maintained with new summaries and concepts
- Concept pages link back to source summaries (`[[summaries/doc_name]]`)
- Summary pages link forward to related concepts (`[[concepts/slug]]`)
- Images are extracted to `sources/images/{doc_name}/` and referenced by path

For querying, use the Obsidian search (Ctrl+O) or the `obsidian-wiki query` command which delegates to the Obsidian CLI.
