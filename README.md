# Obsidian Wiki

Build an Obsidian knowledge base from documents (PDF, Markdown, DOCX, etc.) using an LLM-powered pipeline.

Forked from [OpenKB](https://github.com/VectifyAI/OpenKB) — adapts its compilation workflow for Obsidian vaults, replacing the custom wiki structure with native Obsidian directories.

## Directory Structure (Obsidian vault)

```
vault_root/
  sources/           ← Converted document markdown + images
  summaries/         ← Per-document summary pages
  concepts/         ← Cross-document concept pages (LLM-generated)
  index.md          ← Knowledge base index (auto-maintained)
  .obsidian_wiki/   ← State: hashes.json (do NOT edit manually)
```

## Quick Start

```bash
# Install
pip install -e .

# Set up environment
export LLM_API_KEY=your-key-here

# Add documents
obsidian-wiki add /path/to/document.pdf
obsidian-wiki add /path/to/docs/

# List known documents
obsidian-wiki status
```

## Configuration

Config is stored in `.obsidian_wiki/config.yaml` inside the vault:

```yaml
model: gpt-5.4-mini
language: en
pageindex_threshold: 20
```

Alternatively, set `LLM_API_KEY` in a `.env` file at the vault root.
