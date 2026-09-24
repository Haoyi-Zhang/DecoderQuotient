from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def check(condition: bool, label: str, records: list[dict]) -> None:
    records.append({"check": label, "pass": bool(condition)})
    if not condition:
        raise AssertionError(label)


def page_count(pdf: Path) -> int:
    text = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
    return int(re.search(r"^Pages:\s+(\d+)", text, re.M).group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    records: list[dict] = []

    check({path.name for path in root.iterdir()} == {"paper", "artifact", "research-plan.md", "CURRENT-STATE.md"}, "four-entry project root", records)
    paper = root / "paper"
    artifact = root / "artifact"
    main_pdf = paper / "bit-precise-translation-certificates.pdf"
    supp_pdf = paper / "bit-precise-translation-certificates-supplement.pdf"
    for path in [main_pdf, supp_pdf, paper / "main.tex", paper / "supplement.tex", paper / "references.bib"]:
        check(path.is_file(), f"paper file {path.name}", records)

    # Artifact-only acceptance.
    artifact_report = artifact / "results/publication/publication-acceptance-final.json"
    environment = dict(__import__("os").environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(artifact)
    run = subprocess.run(
        [sys.executable, "tests/publication_acceptance.py", "--root", ".", "--out", str(artifact_report)],
        cwd=artifact,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    check(run.returncode == 0, "artifact publication acceptance", records)

    check(page_count(main_pdf) >= 21, "main PDF has references after content", records)
    check(page_count(supp_pdf) >= 5, "supplement page count", records)
    texts = [
        subprocess.check_output(["pdftotext", "-f", str(page), "-l", str(page), str(main_pdf), "-"], text=True, errors="replace")
        for page in range(1, page_count(main_pdf) + 1)
    ]
    ref_page = next((i + 1 for i, text in enumerate(texts) if re.search(r"\bREFERENCES\b", text, re.I)), None)
    check(ref_page == 21, "exactly 20 content pages", records)
    check(len(re.findall(r"\b\w+\b", texts[19])) >= 220, "substantive final content page", records)

    for pdf in [main_pdf, supp_pdf]:
        fonts = subprocess.check_output(["pdffonts", str(pdf)], text=True, errors="replace")
        lines = [line for line in fonts.splitlines()[2:] if line.strip()]
        check(bool(lines) and not any(re.search(r"\bno\b", line, re.I) for line in lines), f"embedded fonts {pdf.name}", records)
        metadata = subprocess.check_output(["pdfinfo", str(pdf)], text=True, errors="replace")
        author = re.search(r"^Author:\s*(.*)$", metadata, re.M)
        check(author is None or author.group(1).strip() in {"", "Anonymous Author(s)"}, f"anonymous metadata {pdf.name}", records)

    for source in [paper / "main.tex", paper / "supplement.tex"]:
        text = source.read_text(errors="replace").lower()
        for token in ["hyeliozhang", "huaijin003", "gmail.com", "xian jiaotong-liverpool", "nanyang technological"]:
            check(token not in text, f"anonymous source {source.name}: {token}", records)

    check(not list(root.rglob("__pycache__")), "no pycache in project", records)
    check(not list(root.rglob("*.pyc")), "no pyc in project", records)
    check(not list(root.rglob("*.zip")), "no nested archive", records)

    report = {
        "format": "bptc-full-project-acceptance-v1",
        "status": "PASS",
        "checks_passed": sum(record["pass"] for record in records),
        "checks": records,
        "artifact_acceptance_output": run.stdout,
        "main_pages": page_count(main_pdf),
        "content_pages": 20,
        "references_page": ref_page,
        "supplement_pages": page_count(supp_pdf),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
