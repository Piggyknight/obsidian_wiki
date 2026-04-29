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

### Vault-Level LLM Configuration

Instead of (or in addition to) environment variables, you can configure LLM credentials directly in `.obsidian_wiki/config.yaml` under the `llm` key. This takes precedence over all environment variables:

```yaml
llm:
  # API key — works with any provider (OpenAI, Anthropic, OpenRouter, etc.)
  api_key: sk-...
  # Alternative name for api_key (ANTHROPIC_AUTH_TOKEN style)
  auth_token: sk-ant-...
  # Custom base URL — for proxies, OpenRouter, custom endpoints, etc.
  base_url: https://api.openrouter.ai/v1
```

**Priority (highest first):**
1. `llm.api_key` / `llm.auth_token` / `llm.base_url` in `config.yaml`
2. `.env` file in vault root (`vault/.env`)
3. Environment variables (`ANTHROPIC_AUTH_TOKEN`, `LLM_API_KEY`, etc.)

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
ANTHROPIC_AUTH_TOKEN / API Key (saved to config, enter to skip):
Custom base URL (e.g. https://api.openrouter.ai/v1, enter to skip):
Vault root namespace (enter for 'wiki'): wiki
Raw data source directories (comma-separated): ~/research/papers,./notes
```

> **Note:** The API key is saved directly to `.obsidian_wiki/config.yaml` under `llm.auth_token` (or `llm.api_key`), not to a separate `.env` file. This keeps all vault-level configuration in one place.

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

|| Variable | Description |
||----------|-------------|
|| `OBSIDIAN_WIKI_VAULT` | Vault root path (alternative to `--vault`) |
|| `LLM_API_KEY` | Universal API key for LiteLLM (fallback for all providers) |
|| `ANTHROPIC_AUTH_TOKEN` | Anthropic API key (also sets `LLM_API_KEY`) |
|| `OPENAI_API_KEY` | OpenAI API key |
|| `ANTHROPIC_API_KEY` | Anthropic API key |
|| `GEMINI_API_KEY` | Gemini API key |
|| `MINIMAX_API_KEY` | MiniMax API key |
|| `ZHIPU_API_KEY` | Zhipu/GLM API key |
|| `LITELLM_API_BASE` | Custom base URL for LiteLLM (proxies, OpenRouter, etc.) |
|| `PAGEINDEX_API_KEY` | Optional: use PageIndex cloud API instead of local |

> **Tip:** `ANTHROPIC_AUTH_TOKEN` is automatically treated as a universal key — it sets both `ANTHROPIC_API_KEY` and `LLM_API_KEY`, so any model works without extra configuration.

Vault-level config (`.obsidian_wiki/config.yaml` → `llm`) always takes priority over environment variables.

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

---

## Setup Example

Complete walkthrough — from zero to first sync:

**1. Initialize in your vault**

```bash
cd ~/Documents/obsidian_vault
obsidian-wiki init
```

```
Model (enter for default minimax/MiniMax-M2.7): anthropic/claude-sonnet-4-6
ANTHROPIC_AUTH_TOKEN / API Key (saved to config, enter to skip): sk-ant-...
Custom base URL (e.g. https://api.openrouter.ai/v1, enter to skip): https://api.openrouter.ai/v1
Vault root namespace (enter for 'wiki'): wiki
Raw data source directories (comma-separated): ~/research/papers,./notes
```

This creates `.obsidian_wiki/` with `config.yaml` containing your LLM credentials:

```yaml
# .obsidian_wiki/config.yaml
llm:
  auth_token: sk-ant-...
  base_url: https://api.openrouter.ai/v1
```

**2. Configure source directories**

Edit `.obsidian_wiki/config.yaml`:

```yaml
model: minimax/MiniMax-M2.7
language: en
pageindex_threshold: 20

vault:
  root: wiki
  sources: sources
  summaries: summaries
  concepts: concepts
  index: index

sources:
  - ~/research/papers
  - ./notes
```

**4. Sync**

```bash
obsidian-wiki sync
```

```
~/research/papers: 3 supported file(s)
./notes: 2 supported file(s)
Total: 5 file(s) to process

Processing: ~/research/papers/attention_is_all_you_need.pdf
  Adding: attention_is_all_you_need.pdf
  Long document — indexing with PageIndex...
  Compiling (doc_id=doc_001)...
    summary... 1.2s (in=2048, out=128, cached=1024)
    concepts_plan... 0.8s (in=3000, out=64)
    create: transformer-architecture, attention-mechanism
    update: (none)
    related: deep-learning
  Compiling short doc...
. summary... 0.9s (in=1500, out=96)
    [OK] attention_is_all_you_need.pdf added.

Processing: ~/research/papers/llm_survey.md
  Adding: llm_survey.md
  Compiling short doc...
. summary... 0.7s (in=800, out=80)
    [OK] llm_survey.md added.

Done: 5 processed, 0 skipped, 5 total
```

**Resulting vault structure:**

```
obsidian_vault/
├── .obsidian_wiki/
│   ├── config.yaml
│   └── hashes.json
├── .env
└── wiki/
    ├── index.md
    ├── sources/
    │   ├── attention_is_all_you_need.json
    │   └── llm_survey.md
    ├── summaries/
    │   ├── attention_is_all_you_need.md
    │   └── llm_survey.md
    └── concepts/
        ├── transformer-architecture.md
        └── attention-mechanism.md
```
