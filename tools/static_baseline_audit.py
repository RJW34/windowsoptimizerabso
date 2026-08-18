#!/usr/bin/env python3
"""Read-only static baseline audit for WindowsOptimizerAbso.

Parses/compiles source, checks known baseline hazards and placeholders, and
writes JSON. It performs no Windows state mutation.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import py_compile
import sys
from pathlib import Path
from typing import Any

KNOWN_PATTERNS = {
    "fake_rollback_success": "Rollback complete.",
    "missing_backup_call": "create_system_backup(",
    "placeholder_repo_url": "github.com/yourusername/windowsoptimizerabso",
    "placeholder_author": "Your Name",
    "direct_module_preset": "module.apply_preset(",
    "powershell_command": '["powershell", "-Command"',
    "service_disable_command": '["sc", "config"',
    "network_netsh_command": '["netsh"',
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.root.resolve()
    source_root = repo / "src"
    report: dict[str, Any] = {
        "repo": str(repo),
        "python": sys.version,
        "files": [],
        "parse_failures": [],
        "compile_failures": [],
        "pattern_hits": [],
        "missing_expected_paths": [],
    }

    python_files = sorted(source_root.rglob("*.py")) if source_root.exists() else []
    for path in python_files:
        rel = path.relative_to(repo).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            report["parse_failures"].append({"path": rel, "error": f"utf8: {exc}"})
            continue

        report["files"].append({"path": rel, "sha256": sha256(path), "bytes": len(raw)})

        try:
            ast.parse(text, filename=rel)
        except SyntaxError as exc:
            report["parse_failures"].append({
                "path": rel, "line": exc.lineno, "offset": exc.offset, "error": exc.msg
            })

        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            report["compile_failures"].append({"path": rel, "error": str(exc)})

        for name, needle in KNOWN_PATTERNS.items():
            if needle in text:
                report["pattern_hits"].append({"pattern": name, "path": rel})

    for path in [repo / "README.md", repo / "pyproject.toml", repo / "requirements.txt"]:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, needle in KNOWN_PATTERNS.items():
                if needle in text:
                    report["pattern_hits"].append({
                        "pattern": name, "path": path.relative_to(repo).as_posix()
                    })

    for expected in ["tests", ".github/workflows", "LICENSE", "SECURITY.md", "CHANGELOG.md"]:
        if not (repo / expected).exists():
            report["missing_expected_paths"].append(expected)

    report["summary"] = {
        "python_files": len(report["files"]),
        "parse_failures": len(report["parse_failures"]),
        "compile_failures": len(report["compile_failures"]),
        "pattern_hits": len(report["pattern_hits"]),
        "missing_expected_paths": len(report["missing_expected_paths"]),
    }

    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 1 if report["parse_failures"] or report["compile_failures"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
