#!/usr/bin/env python3
"""Read back a release archive, checksums, source hashes and target identity."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
args = parser.parse_args()
for line in (args.directory / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ", 1)
    assert Path(name).name == name, "checksum path must be a basename"
    assert hashlib.sha256((args.directory / name).read_bytes()).hexdigest() == digest, name
provenance = json.loads((args.directory / "PROVENANCE.json").read_text())
archives = list(args.directory.glob("*.tar.gz"))
assert len(archives) == 1
with tarfile.open(archives[0]) as archive:
    members = archive.getmembers()
    assert members and all(member.isfile() for member in members)
    roots = {Path(member.name).parts[0] for member in members}
    assert len(roots) == 1
    content = {}
    for member in members:
        parts = Path(member.name).parts
        assert not Path(member.name).is_absolute() and ".." not in parts
        relative = "/".join(parts[1:])
        assert not {".git", ".venv", "data", "cache", "logs"}.intersection(parts)
        assert Path(relative).name != ".env"
        assert not relative.endswith((".db", ".sqlite", ".log", ".pyc"))
        content[relative] = archive.extractfile(member).read()
    assert json.loads(content["PROVENANCE.json"]) == provenance
    assert json.loads(content["docs/PRODUCTION_SOURCE.json"]) == provenance["production_source"]
    if provenance["target"] == "linux-amd64":
        binary = content["bin/pansou"]
        assert binary[:6] == b"\x7fELF\x02\x01", "ELF64 little-endian expected"
        assert int.from_bytes(binary[18:20], "little") == 62, "amd64 expected"
        assert "LICENSE" in content
    else:
        for path, digest in provenance["production_source"]["files"].items():
            assert hashlib.sha256(content[path]).hexdigest() == digest, path
print("Release verified:", provenance["version"], provenance["revision"], len(content), "files")
