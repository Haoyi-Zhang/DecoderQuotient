"""Artifact-only acceptance checks for the publication result."""
from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path
import re
import subprocess
import sys


def require(condition: bool, message: str, checks: list[dict]) -> None:
    checks.append({"check": message, "pass": bool(condition)})
    if not condition:
        raise AssertionError(message)


def bib_entries(text: str) -> list[tuple[str, str]]:
    entries = []
    pos = 0
    header = re.compile(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,")
    while True:
        match = header.search(text, pos)
        if not match:
            break
        start = match.start()
        brace = text.find("{", start)
        depth = 0
        for index in range(brace, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    entries.append((match.group(1), text[start : index + 1]))
                    pos = index + 1
                    break
        else:
            raise ValueError("unterminated BibTeX entry")
    return entries


def field(block: str, name: str) -> str:
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*([\{\"])", block, re.I)
    if not match:
        return ""
    opener = match.group(1)
    start = match.end()
    if opener == '"':
        end = block.find('"', start)
        return block[start:end]
    depth = 1
    for index in range(start, len(block)):
        if block[index] == "{":
            depth += 1
        elif block[index] == "}":
            depth -= 1
            if depth == 0:
                return block[start:index]
    return ""


def semantic_projection(value):
    if isinstance(value, dict):
        return {
            key: semantic_projection(item)
            for key, item in sorted(value.items())
            if key not in {"run_label", "resource_usage"}
        }
    if isinstance(value, list):
        return [semantic_projection(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    checks: list[dict] = []

    required = [
        "README.md",
        "LICENSE",
        "bptc/publication_campaign.py",
        "bptc/exact_accumulator.py",
        "bptc/accumulator_checker.py",
        "bptc/accumulator_oracle.py",
        "bptc/packed_decoder.py",
        "bptc/source_anchor.py",
        "inputs/omniserve/share_to_reg_one_stage_B.cu",
        "inputs/omniserve/LICENSE",
        "proofs/exact-accumulator-certificates.md",
        "proofs/packed-decoder-closed-form.md",
        "results/publication/combined-summary.json",
        "results/publication/budget.json",
        "evidence/references.bib",
    ]
    for relative in required:
        require((root / relative).is_file(), f"required file: {relative}", checks)

    # Syntax and source hygiene.
    python_files = sorted(root.rglob("*.py"))
    require(bool(python_files), "Python source present", checks)
    for path in python_files:
        text = path.read_text()
        ast.parse(text, filename=str(path))
        require("/mnt/data/" not in text, f"no private absolute path: {path.relative_to(root)}", checks)
        tree = ast.parse(text)
        dangerous = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"eval", "exec"}
        ]
        require(not dangerous, f"no eval/exec: {path.relative_to(root)}", checks)

    require(not list(root.rglob("__pycache__")), "no bytecode cache directories", checks)
    require(not list(root.rglob("*.pyc")), "no bytecode files", checks)
    require(not list(root.rglob("*.zip")), "no nested archives", checks)

    # Every retained machine-readable result parses and every table is rectangular.
    for path in sorted(root.rglob("*.json")):
        json.loads(path.read_text())
    require(True, "all JSON parses", checks)
    for path in sorted(root.rglob("*.csv")) + sorted(root.rglob("*.tsv")):
        delimiter = "\t" if path.suffix == ".tsv" else ","
        rows = list(csv.reader(path.open(), delimiter=delimiter))
        widths = {len(row) for row in rows}
        require(len(widths) <= 1, f"rectangular table: {path.relative_to(root)}", checks)

    combined = json.loads((root / "results/publication/combined-summary.json").read_text())
    budget = json.loads((root / "results/publication/budget.json").read_text())
    main_summary = combined["main_summary"]
    reproduction_summary = combined["reproduction_summary"]
    require(semantic_projection(main_summary) == semantic_projection(reproduction_summary), "semantic clean reproduction", checks)
    require(combined["byte_identical_certificates_and_tables"] is True, "byte-identical certificate/table reproduction", checks)
    require(budget["events_used"] <= budget["limit"], "prospective obligation limit", checks)
    require(budget["status"] == "within-limit", "budget status", checks)
    require(main_summary["decoder"]["cases"] == 30, "30 decoder configurations", checks)
    require(main_summary["accumulator"]["cases"] == 64, "64 accumulator schedules", checks)
    require(main_summary["decoder"]["cross_check_disagreements"] == 0, "decoder cross-check agreement", checks)
    require(main_summary["accumulator"]["cross_check_disagreements"] == 0, "accumulator cross-check agreement", checks)
    require(
        main_summary["decoder"]["certificate_mutations"]
        == main_summary["decoder"]["certificate_mutations_rejected"],
        "all decoder certificate mutations rejected",
        checks,
    )
    require(
        main_summary["accumulator"]["certificate_mutations"]
        == main_summary["accumulator"]["certificate_mutations_rejected"],
        "all accumulator certificate mutations rejected",
        checks,
    )
    source = main_summary["source_anchor"]["mutation_test"]
    require(source["mutations"] == source["rejected"], "all source mutations rejected", checks)

    # Reconfirm actual certificate/table bytes rather than trusting the summary bit.
    for relative in ["accumulator-cases.csv", "decoder-cases.csv"]:
        require(
            (root / "results/publication/main" / relative).read_bytes()
            == (root / "results/publication/reproduction" / relative).read_bytes(),
            f"reproduction bytes: {relative}",
            checks,
        )
    for directory in ["certificates", "decoder-certificates"]:
        left = sorted((root / "results/publication/main" / directory).glob("*.json"))
        right = sorted((root / "results/publication/reproduction" / directory).glob("*.json"))
        require([p.name for p in left] == [p.name for p in right], f"certificate file set: {directory}", checks)
        for a, b in zip(left, right):
            require(a.read_bytes() == b.read_bytes(), f"certificate bytes: {directory}/{a.name}", checks)

    # Bibliography structural audit.
    bib_text = (root / "evidence/references.bib").read_text()
    entries = bib_entries(bib_text)
    require(len(entries) >= 60, "at least 60 bibliography entries", checks)
    keys = [key for key, _ in entries]
    require(len(keys) == len(set(keys)), "unique bibliography keys", checks)
    titles = []
    dois = []
    for key, block in entries:
        title = re.sub(r"[{}\\\s]+", " ", field(block, "title")).strip().lower()
        author = field(block, "author").strip()
        year = field(block, "year").strip()
        require(bool(title), f"bibliography title: {key}", checks)
        require(bool(author) and "and others" not in author.lower(), f"complete named author field: {key}", checks)
        require(bool(re.fullmatch(r"\d{4}", year)), f"four-digit year: {key}", checks)
        titles.append(title)
        doi = field(block, "doi").strip().lower()
        if doi:
            require(doi.startswith("10."), f"DOI syntax: {key}", checks)
            dois.append(doi)
        else:
            stable = any(field(block, name).strip() for name in ["url", "eprint", "isbn"])
            require(stable, f"stable identifier or publisher URL: {key}", checks)
    require(len(titles) == len(set(titles)), "unique normalized bibliography titles", checks)
    require(len(dois) == len(set(dois)), "unique DOI values", checks)

    # Unit tests execute without writing pycache.
    environment = dict(**__import__("os").environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(root)
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", "tests.test_publication_core"],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    require(completed.returncode == 0, "publication unit tests", checks)

    report = {
        "format": "bptc-publication-acceptance-v1",
        "status": "PASS",
        "checks_passed": sum(item["pass"] for item in checks),
        "checks": checks,
        "unit_test_output": completed.stdout,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
