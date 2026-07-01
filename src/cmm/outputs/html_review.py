from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Dict


def build_review_html(manifest: Dict, output_dir: str) -> str:
    data_json = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    body = "\n".join(_segment_html(segment, output_dir) for segment in manifest.get("segments", []))
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ScriptMate Review</title>
  <style>
    :root { color-scheme: light; --ink:#1f2933; --muted:#65758b; --line:#d8dee8; --panel:#f7f9fc; --accent:#0f766e; }
    * { box-sizing: border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }
    header { position:sticky; top:0; z-index:2; padding:16px 24px; border-bottom:1px solid var(--line); background:rgba(255,255,255,.94); }
    h1 { margin:0; font-size:20px; }
    .meta { margin-top:4px; color:var(--muted); font-size:13px; }
    main { max-width:1180px; margin:0 auto; padding:20px 16px 40px; }
    .segment { border:1px solid var(--line); border-radius:8px; margin:0 0 16px; overflow:hidden; }
    .segment-head { display:flex; gap:12px; justify-content:space-between; padding:14px 16px; background:var(--panel); border-bottom:1px solid var(--line); }
    .segment-title { font-weight:700; }
    .pill { display:inline-block; padding:2px 8px; margin-left:6px; border:1px solid var(--line); border-radius:999px; font-size:12px; color:var(--muted); background:#fff; }
    .segment-text { padding:14px 16px; font-size:15px; line-height:1.6; }
    .grid { display:grid; grid-template-columns:minmax(260px, 1fr) 1.2fr; gap:16px; padding:0 16px 16px; }
    .candidate { border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:12px; }
    .candidate h3 { margin:0 0 8px; font-size:15px; }
    .preview { width:100%; max-height:300px; background:#eef2f7; border-radius:6px; object-fit:contain; }
    video.preview { background:#111827; }
    .empty-preview { padding:28px; color:var(--muted); background:#eef2f7; border-radius:6px; text-align:center; }
    dl { display:grid; grid-template-columns:130px 1fr; gap:6px 10px; margin:10px 0 0; font-size:13px; }
    dt { color:var(--muted); }
    dd { margin:0; overflow-wrap:anywhere; }
    a { color:var(--accent); }
    .notes { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:13px; }
    .links { padding:0 16px 16px; font-size:13px; }
    @media (max-width: 760px) { .grid { grid-template-columns:1fr; } .segment-head { display:block; } }
  </style>
</head>
<body>
<header>
  <h1>ScriptMate Review</h1>
  <div class="meta">Created __CREATED_AT__ · Segments __TOTAL_SEGMENTS__</div>
</header>
<main>
__BODY__
</main>
<script type="application/json" id="scriptmate-manifest">__DATA_JSON__</script>
</body>
</html>
"""
    return (
        template.replace("__CREATED_AT__", _escape(str(manifest.get("created_at", ""))))
        .replace("__TOTAL_SEGMENTS__", _escape(str(manifest.get("total_segments", ""))))
        .replace("__BODY__", body)
        .replace("__DATA_JSON__", data_json)
    )


def _segment_html(segment: Dict, output_dir: str) -> str:
    chosen = segment.get("chosen")
    alternatives = segment.get("alternatives") or []
    candidate_html = _candidate_html(chosen, "主选", output_dir) if chosen else '<div class="candidate"><h3>主选</h3><div class="empty-preview">未匹配到可用素材</div></div>'
    alt_html = "\n".join(_candidate_html(candidate, "备选 {0}".format(index), output_dir) for index, candidate in enumerate(alternatives, 1))
    links = "\n".join(
        '<a href="{url}" target="_blank" rel="noreferrer">{name}</a>'.format(
            url=_escape(link.get("url", "")),
            name=_escape(link.get("name", "external")),
        )
        for link in segment.get("external_search_links", [])
    )
    if links:
        links = '<div class="links"><strong>扩展素材库：</strong> {0}</div>'.format(links)
    return """<section class="segment">
  <div class="segment-head">
    <div class="segment-title">段落 {id}<span class="pill">{visual_type}</span><span class="pill">{scene_type}</span></div>
    <div><span class="pill">{confidence}</span><span class="pill">复核 {review}</span></div>
  </div>
  <div class="segment-text">{text}</div>
  <div class="grid">
    <div>
      <dl>
        <dt>角色</dt><dd>{role}</dd>
        <dt>叙事主语</dt><dd>{subject}</dd>
        <dt>策略</dt><dd>{strategy}</dd>
        <dt>建议</dt><dd>{suggestion}</dd>
      </dl>
    </div>
    <div>{candidate_html}{alt_html}</div>
  </div>
  {links}
</section>""".format(
        id=_escape(str(segment.get("id", ""))),
        visual_type=_escape(str(segment.get("type", ""))),
        scene_type=_escape(str(segment.get("scene_type", ""))),
        confidence=_escape(str(segment.get("confidence_band", ""))),
        review=_escape(str(segment.get("review_priority", ""))),
        text=_escape(str(segment.get("text", ""))),
        role=_escape(str(segment.get("segment_role", ""))),
        subject=_escape(str(segment.get("narrative_subject", ""))),
        strategy=_escape(str(segment.get("strategy", ""))),
        suggestion=_escape(str(segment.get("edit_suggestion", ""))),
        candidate_html=candidate_html,
        alt_html=alt_html,
        links=links,
    )


def _candidate_html(candidate: Dict, title: str, output_dir: str) -> str:
    preview = _preview_html(candidate, output_dir)
    notes = candidate.get("score_notes") or []
    notes_html = "".join("<li>{0}</li>".format(_escape(str(note))) for note in notes[:4])
    if notes_html:
        notes_html = '<ul class="notes">{0}</ul>'.format(notes_html)
    return """<article class="candidate">
  <h3>{title}<span class="pill">{source}</span><span class="pill">{tag}</span></h3>
  {preview}
  <dl>
    <dt>分数</dt><dd>{score}</dd>
    <dt>评分方法</dt><dd>{method}</dd>
    <dt>细项</dt><dd>{breakdown}</dd>
    <dt>规格</dt><dd>{resolution} / {orientation}</dd>
    <dt>质量</dt><dd>{quality} / 裁切 {crop}</dd>
    <dt>原因</dt><dd>{reason}</dd>
    <dt>文件/直链</dt><dd><a href="{file}" target="_blank" rel="noreferrer">{file}</a></dd>
    <dt>来源页</dt><dd>{source_page}</dd>
  </dl>
  {notes}
</article>""".format(
        title=_escape(title),
        source=_escape(str(candidate.get("source_label") or candidate.get("source", ""))),
        tag=_escape(str(candidate.get("selection_tag", ""))),
        preview=preview,
        score=_escape(_fmt(candidate.get("score"))),
        method=_escape(str(candidate.get("score_method", ""))),
        breakdown=_escape(_format_breakdown(candidate.get("score_breakdown") or {})),
        resolution=_escape(str(candidate.get("resolution", ""))),
        orientation=_escape(str(candidate.get("orientation", ""))),
        quality=_escape(str(candidate.get("quality_tier", ""))),
        crop=_escape(str(candidate.get("crop_risk", ""))),
        reason=_escape(str(candidate.get("reason", ""))),
        file=_escape(_href(candidate.get("file", ""), output_dir)),
        source_page=_link_or_text(candidate.get("source_page", ""), output_dir),
        notes=notes_html,
    )


def _preview_html(candidate: Dict, output_dir: str) -> str:
    file_value = str(candidate.get("file") or "")
    source = str(candidate.get("source") or "")
    if not file_value:
        return '<div class="empty-preview">无预览</div>'
    href = _href(file_value, output_dir)
    if source.endswith("video") or file_value.lower().split("?")[0].endswith((".mp4", ".mov", ".m4v")):
        return '<video class="preview" src="{0}" controls muted></video>'.format(_escape(href))
    if file_value.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) or source.endswith("image"):
        return '<img class="preview" src="{0}" alt="">'.format(_escape(href))
    return '<div class="empty-preview">无法直接预览，使用下方链接打开</div>'


def _href(value: str, output_dir: str) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    path = Path(value)
    if path.is_absolute():
        return path.as_uri()
    return (Path(output_dir) / path).resolve().as_uri()


def _link_or_text(value: str, output_dir: str) -> str:
    if not value:
        return ""
    href = _href(str(value), output_dir)
    return '<a href="{0}" target="_blank" rel="noreferrer">{1}</a>'.format(_escape(href), _escape(str(value)))


def _format_breakdown(breakdown: Dict) -> str:
    parts = []
    for key in ("semantic", "technical", "local_match", "aspect_fit", "resolution_fit", "duration_fit", "adjustment", "final"):
        if key in breakdown and breakdown[key] not in ("", None):
            parts.append("{0}={1}".format(key, _fmt(breakdown[key])))
    return "; ".join(parts)


def _fmt(value) -> str:
    if isinstance(value, float):
        return "{0:.2f}".format(value)
    return "" if value is None else str(value)


def _escape(value: str) -> str:
    return html.escape(value, quote=True)
