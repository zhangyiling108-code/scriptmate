# Variants

The project now maintains two product variants side by side.

## Script Variant

This is the preserved baseline workflow.

- CLI entry: `cmm run` and `cmm run-script`
- Input: narration script text, `--file`, or `--analysis-file`
- Output: scene analysis, matched candidates, atlas cards, optional CapCut manifest
- Use when you want to plan a video before recording

## Talking Head Video Variant

This is the new workflow built on top of the script matcher.

- CLI entry: `cmm run-video`
- Input: `--video` plus transcript text, `--file`, or `--analysis-file`
- Output: all script variant outputs plus `source_video` metadata and a draft manifest with a `talking_head_base` track
- Use when you already recorded the host video and want the system to enhance it with b-roll, cards, and infographics

## Shared Core

Both variants reuse:

- structured analyzer output
- local library matching
- Pexels and Pixabay retrieval
- atlas card rendering
- ranking and rhythm rules
- CapCut draft packaging

## Current Limitation

The talking-head-video variant does not transcribe audio yet. It expects a transcript or saved analysis as input. The next logical enhancement is automatic transcript generation and time alignment from the source video.
