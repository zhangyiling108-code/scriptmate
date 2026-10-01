# Supported workflow

The current CLI supports `init`, `doctor`, `config-show`, `library-index`, `analyze`, `match`, and `search`.

Use `analyze` to plan materials from a narration script, `match` to create the material package and review page, and `search --media-type image|video` to probe an individual source. See [usage](usage.md) and [open media and vision judging](open-media.md).

Earlier `run-script`, `run-video`, and `run` examples describe an older variant and are not current commands. Automatic transcription, talking-head enhancement, and video shot indexing require separate implementations; the current CLI does not expose those workflows.
