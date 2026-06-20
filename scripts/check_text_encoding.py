from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    "",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {".editorconfig", ".gitattributes", ".gitignore"}
MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "姝ｅ湪", "鏄剧ず鍖哄煙", "閲囨牱")


@dataclass(frozen=True)
class EncodingIssue:
    path: Path
    kind: str
    detail: str


def scan_paths(paths: Iterable[Path]) -> list[EncodingIssue]:
    issues: list[EncodingIssue] = []
    for path in paths:
        if not path.is_file() or not _is_text_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            issues.append(EncodingIssue(path, "invalid_utf8", str(exc)))
            continue
        if "\uFFFD" in text:
            issues.append(EncodingIssue(path, "replacement_character", "contains U+FFFD"))
            continue
        marker = next((candidate for candidate in MOJIBAKE_MARKERS if candidate in text), None)
        if marker:
            issues.append(EncodingIssue(path, "mojibake", f"contains {marker!r}"))
    return issues


def tracked_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _is_text_path(path: Path) -> bool:
    return path.name in TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject non-UTF-8 text and common mojibake.")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    paths = args.paths or tracked_paths(root)
    issues = scan_paths(paths)
    for issue in issues:
        print(f"{issue.path}: {issue.kind}: {issue.detail}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
