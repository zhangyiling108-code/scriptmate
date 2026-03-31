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
- keeps geography, narrative subject, and comparison context aligned
- returns at least 3 real candidates per segment whenever possible
- defaults to **no downgrade** unless the user explicitly allows it
- prefers shareable links first, local downloads second

## Core Output

Each run produces a material package such as:

- `analysis.json`: segment roles, visual types, and search strategy
- `manifest.json`: chosen material, alternatives, reasons, and source links
- `summary.md`: human-readable review report
- `segments_overview.csv`: segment table for bulk review
- `segments/<id>/`: per-segment assets and metadata

## Quick Start

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
.venv/bin/scriptmate --help
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate match --file sample.txt -o ./output
```

For predictable shared setup, prefer `.venv/bin/scriptmate` or activate the virtualenv first.

## Main Commands

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis
.venv/bin/scriptmate match --file sample.txt -o ./output --aspect 9:16 --resolution 1080
.venv/bin/scriptmate search "economic growth" --top 5 --source all --aspect 16:9 --resolution 4K
```

## Configuration

Key configuration sections:

- `[planner_model]`: script analysis model, default `gpt-4.1-mini`
- `[judge_model]`: thumbnail semantic scoring model, default `gpt-4o-mini`
- `[sources]`: enabled providers such as `pexels` and `pixabay`
- `[[sources.extra]]`: domestic, paid, or future libraries declared for routing and extension
- `[matching]`: shortlist size, search depth, score thresholds, aspect, and resolution filters
- `[generation]`: generated fallback behavior, disabled unless explicitly allowed

## Why It Is Different

ScriptMate is optimized for research, explainer, science, medical, and industry-analysis content.

The matching logic emphasizes:

- context over isolated keywords
- narrative correctness over generic “close enough” footage
- geography and subject consistency
- stronger reviewability through structured outputs

## Documentation

- [Chinese overview](README.zh-CN.md)
- [Usage guide](docs/usage.md)
- [Configuration guide](docs/config.md)
- [Deployment guide](docs/deployment.md)

## V1 Scope

Included:

- script analysis into `segment_role` and `visual_type`
- Pexels + Pixabay search
- configurable registration of domestic and paid libraries
- AI semantic scoring
- output package for downstream editing
- bootstrap script and interactive configuration flow

Not included:

- final video rendering as the primary product goal
- AI voiceover
- automatic subtitles
- talking-head-driven workflow as the main path
- complex review UI
