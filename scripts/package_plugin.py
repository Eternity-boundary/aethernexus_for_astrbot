"""Build a reviewable installable archive from an explicit source allowlist.

 Copyright (c) 2026 Skylight Software Organization.
 Created by EternityBoundary
 All rights reserved.
 SPDX-License-Identifier: GPL-3.0-only
 
 File: package_plugin.py
 Project: AetherNexus for AstrBot
"""

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "__init__.py",
    "main.py",
    "client.py",
    "operations.py",
    "service.py",
    "storage.py",
    "workflow.py",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "package.json",
    "README.md",
    "LICENSE",
    "logo.png",
]
sources = [ROOT / name for name in FILES]
for folder, suffixes in {
    "views": {".html", ".js", ".css", ".svg", ".png"},
    ".astrbot-plugin": {".json"},
    "docs": {".md", ".png"},
    "changelogs": {".md"},
    "tests": {".py", ".cjs"},
    "scripts": {".py"},
}.items():
    sources.extend(
        path
        for path in (ROOT / folder).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in suffixes
    )
output = ROOT / "dist" / "aethernexus_for_astrbot-v1.0.0.zip"
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for source in sorted(sources):
        archive.write(source, source.relative_to(ROOT).as_posix())
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert {"main.py", "metadata.yaml", "views/workspace/index.html"} <= set(
        archive.namelist()
    )
print(f"Created {output} ({len(sources)} files)")
print(f"SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")
