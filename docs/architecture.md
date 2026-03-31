# Architecture

The CLI follows a single pipeline:

1. Analyze script into structured segments
2. Match local library assets
3. Query online stock providers
4. Render cards for text-heavy scenes
5. Rank candidates and choose the primary asset
6. Optionally prepare a CapCut draft manifest

`talking_head` is always a placeholder and never auto-filled.
