# ScriptMate CLI

`copy-material-matcher` has been refocused into `ScriptMate CLI`: a script-driven, high-quality material matching engine for short-video workflows.

It does not try to replace CapCut/Jianying video assembly. Instead, it turns a script into a material package that is easier to cut with higher-quality visuals.

## What It Outputs

- `analysis.json`: segment roles, visual types, and search strategy
- `manifest.json`: chosen material, alternatives, reasons, action semantics, and fallback usage
- `summary.md`: human-readable match report
- `segments/<id>/`: per-segment assets and metadata

## Commands

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
.venv/bin/scriptmate match script.txt -o ./output --aspect 9:16 --resolution 1080
.venv/bin/scriptmate analyze script.txt -o ./analysis-output
.venv/bin/scriptmate search "economic growth" --top 5 --source all --aspect 16:9 --resolution 4K
```

`cmm` remains as a compatible entry point:

```bash
cmm match script.txt -o ./output
```

## Quick Start

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis
.venv/bin/scriptmate match --file sample.txt -o ./output
```

The bootstrap script creates a virtual environment, installs dependencies, and seeds `config.toml` from the example template.
For the most predictable shared setup, prefer `.venv/bin/scriptmate` (or activate the virtualenv first) instead of relying on a global `scriptmate` already on PATH.

If you prefer make-style shortcuts:

```bash
make bootstrap
source .venv/bin/activate
make init
make doctor
make help
```

## Config

The CLI uses `config.toml` or `--config`.

Key sections:

- `[planner_model]`: script analysis model, default `gpt-4.1-mini`
- `[judge_model]`: thumbnail scoring model, default `gpt-4o-mini`
- `[sources]`: enabled material providers
- `[[sources.extra]]`: declare domestic, paid, or future libraries without changing the config shape later
- `[matching]`: quality filters and thresholds
  - includes `search_pool_size` so raw search depth is decoupled from final shortlist size
- `[generation]`: fallback chart/card behavior

Operational commands for shared usage:

- `scriptmate init`: interactive config generation
- `scriptmate doctor`: environment and key validation
- `scriptmate config-show`: inspect effective config with masked secrets
- `scriptmate --help`: top-level command and option reference

Detailed usage guide:

- [usage.md](docs/usage.md)
- [config.md](docs/config.md)
- [deployment.md](docs/deployment.md)

## V1 Scope

- Script analysis into `segment_role` and `visual_type`
- Pexels + Pixabay search
- Configurable registration of domestic and paid libraries for per-segment search-link routing and future integration
- AI semantic scoring
- Data chart fallback
- Text card fallback
- Output package for downstream editing
- Bootstrap script + interactive configuration flow

Out of scope for V1:

- Final video rendering
- AI voiceover
- Automatic subtitles
- Talking-head video driven flow
- Complex interactive review UI
