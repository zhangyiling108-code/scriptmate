# Configuration

ScriptMate CLI reads `config.toml` from the project root, or a custom file passed by `--config`.

## Required sections

- `[planner_model]`
  - Used for script analysis
  - Requires `provider`, `model`, `api_key`, `base_url`

- `[judge_model]`
  - Used for thumbnail-based semantic scoring
  - Requires `provider`, `model`, `api_key`, `base_url`

- `[judge]`
  - `vision = false` by default
  - Set `vision = true` only when `judge_model` supports image input
  - Vision judging sends candidate thumbnails to the model and can improve visual accuracy, but it usually consumes more tokens

- `[sources.pexels]`
  - `api_key` for Pexels search

- `[sources.pixabay]`
  - `api_key` for Pixabay search

- `[sources.coverr]`
  - `api_key` for Coverr video search

- `[sources.nasa]`
  - `base_url` for NASA Images search; no API key is required for the built-in integration

- `[[sources.extra]]`
  - Optional declarations for paid or future material libraries
  - Lets you register provider metadata, search URL templates, priority, and env-backed API keys
  - V1 records these providers in config, but does not query them automatically unless an integration is added

## Optional sections

- `[matching]`
  - Thresholds and quality filters
  - Also controls raw provider search depth via `search_pool_size`
  - `target_aspect` records the default material aspect, while `match --aspect` and `search --aspect` require users to choose the actual run aspect

- `[generation]`
  - Chart fallback settings

- `[library]`
  - Local material library path and metadata

- `[cards]`
  - Card size and visual theme

- `[output]`
  - Cache directory and output preferences

## Notes

- Current V1 no longer supports a `mock` provider in runtime behavior.
- The default configuration is optimized for DeepSeek's OpenAI-compatible API.
- Recommended default split:
  - `planner_model = deepseek-v4-flash`
  - `judge_model = deepseek-v4-flash`
- The default `base_url` is `https://api.deepseek.com`; the app appends `/chat/completions` internally.
- If `PLANNER_MODEL_API_KEY` / `JUDGE_MODEL_API_KEY` are not set, the loader will also accept `DEEPSEEK_API_KEY`, then `OPENAI_API_KEY`.
- If `PLANNER_MODEL_BASE_URL` / `JUDGE_MODEL_BASE_URL` are not set, the loader will also accept `DEEPSEEK_BASE_URL`, then `OPENAI_BASE_URL`.
- To enable a vision-capable judge, set `[judge].vision = true`, use `SCRIPTMATE_JUDGE_VISION=true`, or pass `--judge-vision` to `scriptmate match`. This is opt-in because thumbnail image input usually costs more tokens.
- Built-in V1 search providers are `pexels`, `pixabay`, `coverr`, and `nasa`.
- `match` and `search` require `--aspect` so the material package does not mix incompatible ratios. Supported values: `9:16`, `16:9`, `4:3`, `3:4`, `1:1`.
- `matching.search_pool_size` controls how many raw candidates each provider fetches before AI scoring and ranking. The shortlist can stay at 3 while the search pool is larger.
- Use `[[sources.extra]]` to declare additional domestic or paid libraries you want to route or integrate later.
- This is useful for:
  - domestic freemium libraries such as VJ师网/光厂 and 潮点视频
  - paid international libraries such as Pond5, Adobe Stock, Shutterstock, iStock, Artgrid, Storyblocks, or Envato Elements
- Declared extra sources will be available as per-segment search links in output packages once enabled in config.
- Use `scriptmate init --config config.toml` to generate a shareable config interactively.
- Use `scriptmate doctor --config config.toml` to verify Python, config, keys, and matching defaults after setup.
