#!/usr/bin/env python3
"""Full-project packaging and PDF acceptance; no scientific execution."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def capture(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--out", type=Path, default=default_root / "artifact/results/final-acceptance.json")
    args = parser.parse_args()
    root = args.root.resolve()
    checks: list[dict[str, object]] = []

    def require(condition: bool, label: str) -> None:
        checks.append({"check": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    require({path.name for path in root.iterdir()} == {"paper", "artifact", "research-plan.md", "CURRENT-STATE.md"}, "project root contains exactly the four prescribed entries")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "artifact")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "tests/artifact_acceptance.py", "--root", ".", "--out", "results/artifact-acceptance.json"],
        cwd=root / "artifact", env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    require(completed.returncode == 0, "standalone artifact acceptance passes inside the project")

    main_pdf = root / "paper/main.pdf"
    supplement_pdf = root / "paper/supplement.pdf"
    require(main_pdf.is_file() and supplement_pdf.is_file(), "main and supplement PDFs exist")
    main_info = capture(["pdfinfo", str(main_pdf)], root)
    supplement_info = capture(["pdfinfo", str(supplement_pdf)], root)
    main_pages = int(re.search(r"^Pages:\s+(\d+)", main_info, re.M).group(1))
    supplement_pages = int(re.search(r"^Pages:\s+(\d+)", supplement_info, re.M).group(1))
    require(main_pages == 24, "main PDF has 24 total pages")
    require(supplement_pages == 5, "supplement PDF has 5 pages")

    page20 = capture(["pdftotext", "-f", "20", "-l", "20", str(main_pdf), "-"], root)
    page21 = capture(["pdftotext", "-f", "21", "-l", "21", str(main_pdf), "-"], root)
    require("References" not in page20, "references do not begin on content page 20")
    require("References" in page21, "references begin on page 21 after exactly 20 content pages")

    def all_fonts_embedded(pdf: Path) -> bool:
        rows = [line for line in capture(["pdffonts", str(pdf)], root).splitlines()[2:] if line.strip()]
        flags = []
        for line in rows:
            match = re.search(r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$", line)
            if match is None:
                return False
            flags.append(match.group(1) == "yes")
        return bool(flags) and all(flags)

    require(all_fonts_embedded(main_pdf), "all main-PDF fonts are embedded")
    require(all_fonts_embedded(supplement_pdf), "all supplement-PDF fonts are embedded")

    author_line = re.search(r"^Author:\s*(.*)$", main_info, re.M)
    supplement_author_line = re.search(r"^Author:\s*(.*)$", supplement_info, re.M)
    require(author_line is None or not author_line.group(1).strip(), "main PDF metadata has no author identity")
    require(supplement_author_line is None or not supplement_author_line.group(1).strip(), "supplement PDF metadata has no author identity")

    def anonymous_source(path: Path) -> bool:
        source = path.read_text(encoding="utf-8")
        marker = re.search(r"\\author\{([^}]*)\}", source)
        return bool(
            "\\documentclass[acmsmall,screen,review,anonymous,nonacm]{acmart}" in source
            and marker is not None
            and marker.group(1).strip() == "Anonymous Author(s)"
            and "\\affiliation{" not in source
            and re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", source, re.I) is None
        )

    require(anonymous_source(root / "paper/main.tex"), "main source uses the anonymous acmsmall review family and contains no email or affiliation")
    require(anonymous_source(root / "paper/supplement.tex"), "supplement source uses the anonymous acmsmall review family and contains no email or affiliation")

    for name in ("main", "supplement"):
        log = (root / f"paper/{name}.log").read_text(encoding="utf-8", errors="replace")
        require("LaTeX Warning: There were undefined references" not in log, f"{name} LaTeX log has no undefined references")
        require("Citation `" not in log or "undefined" not in log, f"{name} LaTeX log has no undefined citations")
        require("Overfull \\hbox" not in log, f"{name} LaTeX log has no horizontal overflow")

    report = {
        "audit_kind": "full project and PDF acceptance",
        "scientific_execution": False,
        "passed": True,
        "checks_passed": len(checks),
        "checks": checks,
        "summary": {"main_pages": main_pages, "content_pages": 20, "reference_pages": 4, "supplement_pages": supplement_pages},
    }
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "checks_passed": len(checks), **report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
        print(f"final acceptance failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
