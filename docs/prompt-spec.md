# Prompt Spec

The analyzer prompt must return strict JSON with:

- `segments`
- `overall_style`
- `target_aspect`

Each segment must include:

- `id`
- `text`
- `scene_type`
- `duration_hint`
- `search_queries`
- `keywords_cn`
- `keywords_en`
- `card_text`
- `visual_brief`
