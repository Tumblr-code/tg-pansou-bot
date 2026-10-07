# Repository workflow

- Preserve the verified production runtime source for this release. Documentation, tests, packaging and CI may change; a runtime change requires a separately scoped request and deployment validation.
- Use short-lived `codex/` branches and PRs. After review and successful required checks for the exact PR head, merge into `main` without asking again, then delete the merged remote branch. Never bypass branch protection or failed checks.
- Keep third-party attribution and existing license terms. Do not add a license to an unlicensed project on the owner's behalf.
- Production access is read-only during documentation and release work. A GitHub release does not deploy or restart services.
- Never commit real environment files, tokens, user data, databases, caches or logs. Preserve unique unmerged branches and other tasks' worktrees.
