# ScriptMate CLI

**English** | [简体中文](README.zh-CN.md)

ScriptMate is a script-driven, high-quality material matching engine for short-video workflows.

It does not try to replace a video editor. Instead, it turns a script into a material package with stronger search strategy, better candidate quality, and clearer review outputs.

## Product Intro

![ScriptMate cover](docs/assets/intro/01-cover-scriptmate-intro.png)

![ScriptMate comparison](docs/assets/intro/02-comparison-scriptmate-intro.png)

![ScriptMate features](docs/assets/intro/03-features-scriptmate-intro.png)

![ScriptMate ending](docs/assets/intro/04-ending-scriptmate-intro.png)

## What ScriptMate Does

- analyzes a script into semantic segments
- decides the right visual lane for each segment
- searches real footage and image sources with context-aware queries
- prioritizes owned assets through a cached local library index
- keeps geography, narrative subject, and comparison context aligned
- returns at least 3 real candidates per segment whenever possible
- exposes semantic, technical, and local-match scoring details for review
- defaults to **no downgrade** unless the user explicitly allows it
- prefers shareable links first, local downloads second

## Core Output

Each run produces a material package such as:

- `analysis.json`: segment roles, visual types, and search strategy
- `manifest.json`: chosen material, alternatives, reasons, and source links
- `summary.md`: human-readable review report
- `review.html`: offline static review page with previews, chosen/alternative candidates, score details, and source links
- `segments_overview.csv`: segment table for bulk review
- `segments/<id>/`: per-segment assets and metadata

## Quick Start

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
.venv/bin/scriptmate --help
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate match --file sample.txt -o ./output --aspect 9:16
```

For predictable shared setup, prefer `.venv/bin/scriptmate` or activate the virtualenv first.

## Main Commands

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis
.venv/bin/scriptmate match --file sample.txt -o ./output --aspect 9:16 --resolution 1080
.venv/bin/scriptmate match --file sample.txt -o ./output --aspect 9:16 --library-root ./materials --library-meta ./materials.csv
.venv/bin/scriptmate library-index --root ./materials --metadata ./materials.csv --output ./materials/index.json
.venv/bin/scriptmate search "economic growth" --top 5 --source all --aspect 16:9 --resolution 4K
```

## Local Library and Review Page

The local library workflow is designed for owned footage, licensed assets, reusable B-roll, and brand materials. When `--library-root` is provided, ScriptMate automatically creates and reuses a `.scriptmate-library-index.json` index with file paths, titles, descriptions, tags, categories, dimensions, duration, aspect ratio, orientation, searchable text, and fingerprints.

To prebuild or inspect the index, run:

```bash
.venv/bin/scriptmate library-index --root ./materials --metadata ./materials.csv
```

Metadata can be CSV or JSONL and is matched by relative path. CSV example:

```csv
path,title,description,tags,category
city/shanghai.mp4,Shanghai skyline,China city economy and modernization footage,china|economy|city,city
```

Match outputs now keep transparent score fields in `manifest.json`, `segments_overview.csv`, `summary.md`, and `review.html`, including `semantic_score`, `technical_score`, `local_match_score`, `aspect_fit`, `score_method`, and `score_notes`. `review.html` is a static file that can be opened directly in a browser to inspect each segment's chosen candidate, alternatives, preview media, score rationale, and source links.

## Configuration

Key configuration sections:

- `[planner_model]`: script analysis model, default `deepseek-v4-flash`
- `[judge_model]`: candidate semantic scoring model, default `deepseek-v4-flash`
- `[judge]`: optional judge behavior; `vision = true` sends thumbnails to a vision-capable judge and usually uses more tokens
- `[sources]`: enabled providers such as `pexels`, `pixabay`, `coverr`, and `nasa`
- `[[sources.extra]]`: domestic, paid, or future libraries declared for routing and extension
- `[library]`: optional local material library root and metadata file; can also be overridden with `--library-root` and `--library-meta`
- `[matching]`: shortlist size, search depth, score thresholds, aspect, and resolution filters
- Material search requires `--aspect`; supported ratios are `9:16`, `16:9`, `4:3`, `3:4`, and `1:1`
- `[generation]`: generated fallback behavior, disabled unless explicitly allowed

## Why It Is Different

ScriptMate is optimized for research, explainer, science, medical, and industry-analysis content.

The matching logic emphasizes:

- context over isolated keywords
- narrative correctness over generic “close enough” footage
- geography and subject consistency
- owned assets through a reusable local index
- transparent scoring rationale for human review
- stronger reviewability through structured outputs

## Documentation

- [Chinese overview](README.zh-CN.md)
- [Usage guide](docs/usage.md)
- [Configuration guide](docs/config.md)
- [Deployment guide](docs/deployment.md)

## V1 Scope

Included:

- script analysis into `segment_role` and `visual_type`
- Pexels + Pixabay + Coverr + NASA Images search
- local library indexing, caching, and multidimensional matching
- static HTML review page
- configurable registration of domestic and paid libraries
- AI semantic scoring with score-detail outputs
- output package for downstream editing
- bootstrap script and interactive configuration flow

Not included:

- final video rendering as the primary product goal
- AI voiceover
- automatic subtitles
- talking-head-driven workflow as the main path
- complex review UI
