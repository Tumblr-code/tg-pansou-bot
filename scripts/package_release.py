#!/usr/bin/env python3
"""Build a release from committed, allowlisted source; never read live configuration."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PROJECT = "tg-pansou-bot"
ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def package(version: str, output: Path) -> None:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise SystemExit("version must be a final vMAJOR.MINOR.PATCH")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("commit tracked changes before packaging")
    revision = git("rev-parse", "HEAD").decode().strip()
    epoch = int(git("show", "-s", "--format=%ct", "HEAD"))
    suffix = "linux-amd64" if PROJECT == "pansou" else "source"
    name = f"{PROJECT}-{version}-{suffix}"
    output.mkdir(parents=True, exist_ok=True)
    payload: dict[str, bytes] = {}
    tracked = git("ls-tree", "-r", "--name-only", "HEAD").decode().splitlines()
    roots = {"README.md", "README.en.md", "UPSTREAM_README.zh-CN.md", "LICENSE",
             "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "DEPLOY.md"}
    for path in tracked:
        allowed = path in roots or path.startswith(("docs/", "deploy/"))
        if PROJECT != "pansou":
            allowed = allowed or path.startswith(("src/", "scripts/", "tests/")) or path in {
                "main.py", "requirements.txt", "requirements-dev.txt", "pyproject.toml",
                ".env.example", "Dockerfile", "docker-compose.yml", "start.sh"}
        if allowed:
            payload[path] = git("show", "HEAD:" + path)
    manifest = json.loads(payload["docs/PRODUCTION_SOURCE.json"])
    provenance = {
        "schema": 1, "repository": "https://github.com/Tumblr-code/" + PROJECT,
        "version": version, "revision": revision, "target": suffix,
        "source_date_epoch": epoch, "production_source": manifest,
        "production_deployed_by_this_release": False,
        "license": "MIT" if PROJECT == "pansou" else "not declared by repository owner",
    }
    if PROJECT == "pansou":
        with tempfile.TemporaryDirectory(prefix="pansou-release-source-") as directory:
            source = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(git("archive", "HEAD"))) as archive:
                archive.extractall(source, filter="data")
            subprocess.run([sys.executable, "scripts/verify_production_source.py"],
                           cwd=source, check=True)
            env = dict(os.environ, CGO_ENABLED="0", GOOS="linux", GOARCH="amd64",
                       GOTOOLCHAIN="local")
            binary = source / "pansou-release-bin"
            subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-ldflags=-s -w",
                            "-o", str(binary), "."], cwd=source, env=env, check=True)
            payload["bin/pansou"] = binary.read_bytes()
            provenance["build_toolchain"] = subprocess.check_output(
                ["go", "version"], text=True).strip()
            modules = subprocess.check_output(["go", "list", "-m", "-json", "all"],
                                              cwd=source, env=env, text=True)
            decoder = json.JSONDecoder()
            remaining = modules.lstrip()
            dependencies = []
            while remaining:
                module, end = decoder.raw_decode(remaining)
                remaining = remaining[end:].lstrip()
                if module.get("Main"):
                    continue
                dependencies.append({"path": module["Path"], "version": module.get("Version")})
                module_dir = Path(module.get("Dir", "/nonexistent"))
                for license_name in ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "NOTICE"]:
                    license_file = module_dir / license_name
                    if license_file.is_file():
                        payload["THIRD_PARTY_LICENSES/" + module["Path"] + "/" + license_name] = (
                            license_file.read_bytes())
            provenance["dependencies"] = dependencies
    else:
        for path, digest in manifest["files"].items():
            if hashlib.sha256(payload[path]).hexdigest() != digest:
                raise SystemExit("production source mismatch: " + path)
        provenance["build_toolchain"] = "Python " + sys.version.split()[0]
    provenance_bytes = (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode()
    payload["PROVENANCE.json"] = provenance_bytes
    archive_path = output / (name + ".tar.gz")
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path, content in sorted(payload.items()):
                    info = tarfile.TarInfo(name + "/" + path)
                    info.size = len(content)
                    info.mode = 0o755 if path == "bin/pansou" or path.endswith(".sh") else 0o644
                    info.mtime = epoch
                    archive.addfile(info, io.BytesIO(content))
    (output / "PROVENANCE.json").write_bytes(provenance_bytes)
    assets = [archive_path, output / "PROVENANCE.json"]
    (output / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
        for path in assets))
    print(archive_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    arguments = parser.parse_args()
    package(arguments.version, arguments.output)
