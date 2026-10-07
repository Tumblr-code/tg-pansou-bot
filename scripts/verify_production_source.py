#!/usr/bin/env python3
"""Verify the release runtime against the read-only production source manifest."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / "docs/PRODUCTION_SOURCE.json").read_text())
expected = manifest["files"]
if manifest["runtime_kind"] == "go":
    actual = {str(p.relative_to(root)) for p in root.rglob("*.go")
              if not {".git", "dist", ".release-check"}.intersection(p.relative_to(root).parts)}
    actual.update({"go.mod", "go.sum"})
else:
    actual = {str(p.relative_to(root)) for p in (root / "src").rglob("*.py")}
    actual.update({"main.py", "requirements.txt"})
errors = ["runtime path set differs"] if actual != set(expected) else []
for name, digest in expected.items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        errors.append("runtime hash differs: " + name)
if errors:
    raise SystemExit("\n".join(errors))
print(f"Production source verified: {len(expected)} files")
