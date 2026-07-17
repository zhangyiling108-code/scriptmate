# ScriptMate Universal Skill Distribution Design

## Goal

Publish the latest ScriptMate implementation from the maintained GitHub repository while also exposing a small, platform-neutral Skill package that can be discovered and installed independently.

## Source of Truth

- Treat `/Users/joker/Downloads/scriptmate/` as the source for the latest functional changes in this synchronization.
- Keep the GitHub repository root as the canonical application source.
- Import only source code, tests, dependency metadata, and reusable runtime scripts.
- Exclude generated outputs, local environments, caches, archives, sample runs, and process-only packaging notes.

## Repository Layout

```text
scriptmate/
├── src/                       # Canonical Python application
├── scripts/                   # Repository development/runtime helpers
├── tests/                     # Application tests
├── skills/
│   └── scriptmate/
│       ├── SKILL.md           # Generic agent instructions
│       └── scripts/
│           ├── bootstrap.sh   # Install or update a cached runtime
│           └── scriptmate.sh  # Run the installed CLI
└── pyproject.toml             # Canonical package metadata
```

The repository root will not contain `SKILL.md`. This prevents a Skill registry from treating the complete project, including documentation media, as one oversized Skill package.

## Skill Contract

The Skill package must:

- Use only `name` and `description` in YAML frontmatter.
- Describe when to invoke ScriptMate and the inputs it requires.
- Use imperative instructions and remain concise.
- Avoid assumptions about a particular agent product, registry, uploader, or authentication flow.
- Keep generated media and downloaded footage outside the Skill directory.

## Runtime Flow

1. The agent reads `SKILL.md` and gathers the source video, transcript or script, output directory, and optional configuration.
2. `bootstrap.sh` checks for Python, Git, and FFmpeg, then clones or updates the canonical public repository in a user cache directory.
3. The bootstrap creates an isolated virtual environment and installs ScriptMate from the checked-out source.
4. `scriptmate.sh` delegates all CLI arguments to the cached installation.
5. ScriptMate writes project output only to the user-selected output directory.

When the Skill is executed from a full repository checkout, the scripts may use that checkout directly. When installed as a standalone Skill folder, they obtain the application from GitHub.

## Update and Failure Behavior

- Use fast-forward-only Git updates; never rewrite a user's local repository state.
- Preserve the last working cached runtime if a network update fails.
- Print actionable errors for missing Python, Git, FFmpeg, repository access, dependency installation, and invalid CLI arguments.
- Allow environment-variable overrides for the repository URL, revision, cache directory, and Python executable so forks and pinned deployments remain possible.

## Synchronization Rules

- Copy the latest functional changes into a clean worktree based on `origin/main`.
- Preserve unrelated files in the user's existing worktree.
- Do not import generated artifacts or platform-specific publishing instructions.
- Commit normally and push with a non-force update to `main` only after verification succeeds.

## Verification

Before publishing:

1. Validate `skills/scriptmate/SKILL.md` with the standard Skill validator.
2. Scan tracked content for registry- or vendor-specific terminology.
3. Run the Python test suite in an isolated environment.
4. Run shell syntax checks for both Skill scripts.
5. Exercise bootstrap and CLI help through a temporary cache.
6. Confirm the Skill directory stays below registry file-count and archive-size limits.
7. Confirm the final Git diff contains no generated outputs or unrelated local files.
