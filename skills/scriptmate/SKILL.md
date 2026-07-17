---
name: scriptmate
description: Use when an agent needs to turn a video script or transcript into a reviewable material-matching package, analyze visual segments, search stock footage or images, index a licensed local media library, inspect scoring decisions, configure providers, or troubleshoot the ScriptMate CLI.
---

# ScriptMate

Use ScriptMate to convert a script into semantic segments, visual strategies, ranked footage or image candidates, source links, transparent scores, and review files.

## Prepare

Resolve the directory containing this `SKILL.md`, change to that directory, and verify the launcher:

```bash
scripts/scriptmate.sh --help
```

The launcher requires Python 3.9 or newer, Git, and FFmpeg. It uses the enclosing repository when available; otherwise it installs the canonical ScriptMate source into a user cache. Override the source with `SCRIPTMATE_SOURCE_DIR`, or override the repository, revision, cache, or Python executable with `SCRIPTMATE_REPOSITORY_URL`, `SCRIPTMATE_REVISION`, `SCRIPTMATE_CACHE_DIR`, or `SCRIPTMATE_PYTHON`.

Before running a task, gather:

- Script text or a UTF-8 text file.
- Output directory.
- Aspect ratio: `9:16`, `16:9`, `4:3`, `3:4`, or `1:1`.
- Preferred resolution: `4K`, `1080`, or `720`.
- Optional provider configuration and licensed local media library.

## Configure and Diagnose

Create a configuration file when needed, then inspect it without exposing secrets:

```bash
scripts/scriptmate.sh init --config config.toml --non-interactive
scripts/scriptmate.sh doctor --config config.toml
scripts/scriptmate.sh config-show --config config.toml
```

Supply API keys through environment variables or an ignored local `config.toml`. Prefer `config-show` for inspection because it masks credentials.

## Run the Workflow

Analyze a script without searching for materials:

```bash
scripts/scriptmate.sh analyze --file script.txt -o ./analysis-output --aspect 9:16 --config config.toml
```

Index a local media library:

```bash
scripts/scriptmate.sh library-index --root /path/to/library --metadata /path/to/metadata.csv
```

Generate a complete material-matching package:

```bash
scripts/scriptmate.sh match --file script.txt -o ./output --top 3 --aspect 9:16 --resolution 1080 --config config.toml
```

Add `--library-root` and `--library-meta` to include owned or licensed local assets. Probe a single search query with:

```bash
scripts/scriptmate.sh search "economic growth" --top 5 --source all --aspect 16:9 --resolution 4K --config config.toml
```

Explain before network-backed commands that provider calls can consume API quota. Keep `--download` disabled unless local media files are explicitly required.

## Review Results

Review outputs in this order:

1. Open `summary.md` for the editorial overview.
2. Open `review.html` for a visual, static review surface.
3. Inspect `manifest.json` for exact selections, alternatives, scores, reasons, and source URLs.
4. Inspect `segments_overview.csv` and per-segment JSON for bulk or detailed review.

Treat automatically selected materials as recommendations. Verify relevance, licensing, attribution, and factual fit before publishing.

## Guardrails

- Do not silently enable planner, judge, search, or generated-material fallbacks. Obtain explicit acceptance before adding any `--allow-*-fallback` option.
- Do not print full credentials or commit a populated `config.toml`.
- Enable judge vision only when the configured model supports images and higher token usage is acceptable.
- Report provider, network, quota, FFmpeg, and configuration failures directly instead of claiming success.
- Preserve source links and attribution requirements in the generated review package.
