# Deployment Guide

## Minimum requirements

- macOS or Linux
- Python 3.9+
- Network access for:
  - planner model
  - judge model
  - stock libraries

## Fastest setup

```bash
cd /path/to/scriptmate
bash scripts/bootstrap.sh
source .venv/bin/activate
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
```

Or use the included shortcuts:

```bash
cd /path/to/scriptmate
make bootstrap
source .venv/bin/activate
make init
make doctor
```

## What `bootstrap.sh` does

1. checks Python version
2. creates `.venv`
3. installs ScriptMate with dev dependencies
4. creates `config.toml` from `config.example.toml` if missing

Using `.venv/bin/scriptmate` avoids conflicts with any older global `scriptmate` command that may already exist on a machine.

## Recommended first-run workflow

```bash
.venv/bin/scriptmate init --config config.toml
.venv/bin/scriptmate doctor --config config.toml
.venv/bin/scriptmate config-show --config config.toml
.venv/bin/scriptmate analyze --file sample.txt -o ./analysis
.venv/bin/scriptmate match --file sample.txt -o ./output
```

## Environment variables

For a shareable setup, prefer environment variables over committing real keys into `config.toml`.

Available variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `PLANNER_MODEL_API_KEY`
- `PLANNER_MODEL_BASE_URL`
- `JUDGE_MODEL_API_KEY`
- `JUDGE_MODEL_BASE_URL`
- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `VJSHI_API_KEY`
- `SHIPIN520_API_KEY`
- `POND5_API_KEY`
- `ADOBE_STOCK_API_KEY`

You can start from:

```bash
cp .env.example .env
```

## Notes for sharing with other users

- Prefer environment variables for real API keys when possible.
- `scriptmate config-show` masks secrets when printing config summaries.
- `scriptmate doctor` is the quickest way to confirm an environment is ready before debugging deeper issues.
