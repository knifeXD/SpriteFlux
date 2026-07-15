#!/usr/bin/env python3
"""Fail when tracked Skill files resemble secrets or private generation artifacts."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


FORBIDDEN_NAMES = [
    re.compile(r"(^|/)(\.env($|\.)|private|\.private|\.secrets|runs|downloads|outputs|work|artifacts)(/|$)", re.I),
    re.compile(r"(^|/)(task-response|create-response|receipt|request-preview).*\.json$", re.I),
    re.compile(r"\.(mp4|mov|webm|pem|key|p12)$", re.I),
]

SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider-task-id": re.compile(r"\bcgt-\d{8,}-[A-Za-z0-9]+\b"),
    "literal-bearer": re.compile(r"authorization:\s*bearer\s+(?!\$|<|\{|\[)[A-Za-z0-9._-]{12,}", re.I),
    "literal-api-assignment": re.compile(
        r"(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"']"
        r"(?!\$|<|your-|example-|replace-|在本机)[A-Za-z0-9_./+=-]{12,}[\"']",
        re.I,
    ),
    "signed-url": re.compile(r"(?:X-Amz-Signature|X-Tos-Signature|Signature)=[A-Fa-f0-9%]{16,}"),
}


def tracked_files(root: Path) -> list[Path]:
    try:
        output = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
        return [root / item.decode("utf-8") for item in output.split(b"\0") if item]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]


def audit(root: Path) -> list[str]:
    findings: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if any(pattern.search(relative) for pattern in FORBIDDEN_NAMES):
            findings.append(f"forbidden tracked path: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label}: {relative}")
    return findings


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "safe.md").write_text("Use Authorization: Bearer $ARK_API_KEY and never paste it.", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "safe.md"], check=True)
        assert audit(root) == []
        (root / "unsafe.txt").write_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "unsafe.txt"], check=True)
        assert any("literal-bearer" in item for item in audit(root))
    print("audit_publication_safety self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit tracked Skill files before publication")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    findings = audit(args.root.resolve())
    if findings:
        for finding in findings:
            print("ERROR", finding)
        raise SystemExit(1)
    print(f"publication safety audit: ok ({len(tracked_files(args.root.resolve()))} tracked files)")


if __name__ == "__main__":
    main()

