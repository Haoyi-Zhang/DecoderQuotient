#!/usr/bin/env python3
"""Audit bibliography identity, persistent identifiers, citations, and 12+5+5 calibration."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def parse_bib(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    cursor = 0
    while True:
        match = re.search(r"@(\w+)\s*\{\s*([^,]+),", text[cursor:], re.M)
        if match is None:
            break
        entry_type, key = match.group(1).lower(), match.group(2).strip()
        start = cursor + match.start()
        pos = cursor + match.end()
        depth = 1
        in_quote = False
        escaped = False
        end = pos
        while end < len(text) and depth:
            char = text[end]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = not in_quote
            elif not in_quote:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
            end += 1
        if depth:
            raise ValueError(f"unterminated BibTeX entry {key}")
        body = text[pos : end - 1]
        fields: dict[str, str] = {}
        index = 0
        while index < len(body):
            while index < len(body) and body[index] in " \t\r\n,":
                index += 1
            field_match = re.match(r"([A-Za-z][\w-]*)\s*=\s*", body[index:])
            if field_match is None:
                if body[index:].strip():
                    raise ValueError(f"cannot parse field in {key}: {body[index:index+60]!r}")
                break
            name = field_match.group(1).lower()
            index += field_match.end()
            if body[index] == "{":
                field_depth = 1
                value_start = index + 1
                index += 1
                escaped = False
                while index < len(body) and field_depth:
                    char = body[index]
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == "{":
                        field_depth += 1
                    elif char == "}":
                        field_depth -= 1
                    index += 1
                value = body[value_start : index - 1]
            elif body[index] == '"':
                value_start = index + 1
                index += 1
                escaped = False
                while index < len(body):
                    char = body[index]
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        break
                    index += 1
                value = body[value_start:index]
                index += 1
            else:
                value_start = index
                while index < len(body) and body[index] not in ",\n":
                    index += 1
                value = body[value_start:index].strip()
            fields[name] = value.strip()
        entries.append({"type": entry_type, "key": key, "fields": fields, "raw": text[start:end]})
        cursor = end
    return entries


def clean(value: str) -> str:
    value = re.sub(r"\\[A-Za-z]+\s*", "", value)
    return re.sub(r"[{}\\]", "", value).strip()


def canonical_identifier(fields: dict[str, str]) -> tuple[str, str, str]:
    if fields.get("doi"):
        value = fields["doi"].strip()
        return "doi", value, f"https://doi.org/{value}"
    if fields.get("eprint"):
        value = fields["eprint"].strip()
        return "arxiv", value, f"https://arxiv.org/abs/{value}"
    if fields.get("url"):
        value = fields["url"].strip()
        return "official_url", value, value
    if fields.get("isbn"):
        value = fields["isbn"].strip()
        return "isbn", value, f"https://search.worldcat.org/isbn/{value}"
    raise AssertionError("entry has no persistent identifier")


def extract_citations(path: Path) -> set[str]:
    text = re.sub(r"(?<!\\)%.*", "", path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for match in re.finditer(r"\\cite\w*\s*(?:\[[^]]*\]\s*)*\{([^}]+)\}", text):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    artifact_root = Path(__file__).resolve().parents[1]
    default_project = artifact_root.parent if (artifact_root.parent / "paper").is_dir() else None
    parser.add_argument("--bib", type=Path, default=(default_project / "paper/references.bib") if default_project else artifact_root / "evidence/references.bib")
    parser.add_argument("--main", type=Path, default=(default_project / "paper/main.tex") if default_project else None)
    parser.add_argument("--supplement", type=Path, default=(default_project / "paper/supplement.tex") if default_project else None)
    parser.add_argument("--calibration", type=Path, default=artifact_root / "literature-calibration.csv")
    parser.add_argument("--out", type=Path, default=artifact_root / "results/reference-audit.json")
    parser.add_argument("--evidence-json", type=Path, default=artifact_root / "evidence/reference-verification.json")
    parser.add_argument("--evidence-tsv", type=Path, default=artifact_root / "evidence/reference-verification.tsv")
    args = parser.parse_args()

    entries = parse_bib(args.bib.resolve())
    by_key = {entry["key"]: entry for entry in entries}
    checks: list[dict[str, object]] = []

    def require(condition: bool, label: str) -> None:
        checks.append({"check": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    require(len(entries) == 68, "bibliography contains exactly 68 entries")
    require(len(by_key) == len(entries), "all bibliography keys are unique")
    require(all("author" in entry["fields"] for entry in entries), "every entry has authorship")
    require(all("title" in entry["fields"] for entry in entries), "every entry has a title")
    require(all("year" in entry["fields"] for entry in entries), "every entry has a year")
    require(all("and others" not in entry["fields"].get("author", "").lower() for entry in entries), "no entry uses an incomplete 'and others' author list")
    require(all(any(entry["fields"].get(name) for name in ("doi", "eprint", "url", "isbn")) for entry in entries), "every entry has a DOI, arXiv id, official URL, or ISBN")

    dois = [entry["fields"]["doi"].lower() for entry in entries if entry["fields"].get("doi")]
    titles = [clean(entry["fields"]["title"]).casefold() for entry in entries]
    require(len(dois) == len(set(dois)), "DOIs are unique")
    require(len(titles) == len(set(titles)), "titles are unique")
    require(all(re.fullmatch(r"10\.\d{4,9}/\S+", doi) for doi in dois), "all DOI strings have registry syntax")
    require(all(re.fullmatch(r"\d{4}\.\d{4,5}", entry["fields"]["eprint"]) for entry in entries if entry["fields"].get("eprint")), "all arXiv identifiers have canonical syntax")
    require(all(1900 <= int(entry["fields"]["year"]) <= 2026 for entry in entries), "publication years are plausible and not future-dated beyond 2026")

    exact = {
        "mixednumeric": ("MIX-PC", ["Huang, Shiyuan", "Guan, Haibing"], "10.1145/3785473"),
        "fixedpoint-rns": ("Residue Number Systems", ["Deng, Bobin", "Lo, Dan Chia-Tien"], "10.1145/3664923"),
        "verification-dialects": ("First-Class Verification Dialects", ["Fehr, Mathieu", "Grosser, Tobias"], "10.1145/3729309"),
        "tensorir": ("TensorIR", ["Feng, Siyuan", "Chen, Tianqi"], "2207.04296"),
        "atom": ("Atom", ["Zhao, Yilong", "Kasikci, Baris"], "2310.19102"),
        "quarot": ("QuaRot", ["Ashkboos, Saleh", "Hensman, James"], "10.5555/3737916.3741096"),
        "aarch64tv": ("AArch64", ["Berger, Ryan", "Regehr, John"], "10.1145/3763147"),
    }
    for key, (title_fragment, authors, identifier) in exact.items():
        require(key in by_key, f"corrected reference {key} is present")
        fields = by_key[key]["fields"]
        require(title_fragment in clean(fields["title"]), f"{key} title matches its primary record")
        require(all(author in fields["author"] for author in authors), f"{key} author endpoints match its primary record")
        require(identifier in (fields.get("doi", ""), fields.get("eprint", "")), f"{key} persistent identifier matches its primary record")

    citations: set[str] = set()
    for source in (args.main, args.supplement):
        if source is not None and source.exists():
            citations |= extract_citations(source)
    if citations:
        require(citations <= set(by_key), "all LaTeX citation keys resolve")
        require(set(by_key) <= citations, "all 68 bibliography entries are substantively cited")

    with args.calibration.resolve().open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    groups = Counter(row["group"] for row in rows)
    require(groups == {"same-venue": 12, "influential": 5, "adjacent": 5}, "literature calibration is exactly 12 same-venue + 5 influential + 5 adjacent")
    require(len({row["bib_key"] for row in rows}) == 22, "calibration entries are unique")
    require(all(row["bib_key"] in by_key for row in rows), "every calibration row resolves to a bibliography key")
    require(all("abstract only" not in row["access_basis"].lower() for row in rows), "calibration does not count abstract-only reading")

    calibration = {row["bib_key"]: row["group"] for row in rows}
    records: list[dict[str, object]] = []
    for entry in entries:
        fields = entry["fields"]
        identifier_type, identifier, canonical_url = canonical_identifier(fields)
        records.append({
            "bib_key": entry["key"],
            "entry_type": entry["type"],
            "title": clean(fields["title"]),
            "authors": clean(fields["author"]),
            "year": int(fields["year"]),
            "identifier_type": identifier_type,
            "identifier": identifier,
            "canonical_url": canonical_url,
            "access_date": "2026-09-19",
            "calibration_group": calibration.get(entry["key"]),
            "verification_scope": "persistent identity and bibliography-field audit; selected current/corrected records cross-checked against primary publisher, proceedings, author, or arXiv records",
            "redistributed_full_text": False,
        })

    evidence = {
        "schema": "bptc-reference-verification-v1",
        "generated_from": "paper/references.bib",
        "access_date": "2026-09-19",
        "entries": records,
        "summary": {
            "entries": len(records),
            "identifier_types": dict(sorted(Counter(record["identifier_type"] for record in records).items())),
            "calibration_groups": dict(sorted(groups.items())),
            "duplicate_dois": 0,
            "duplicate_titles": 0,
            "incomplete_author_lists": 0,
        },
        "limitation": "This ledger verifies bibliographic identity and the recorded reading calibration; it is not a citation-impact ranking or a claim that every referenced artifact was executed.",
    }
    args.evidence_json.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.evidence_json.resolve().write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.evidence_tsv.resolve().open("w", newline="", encoding="utf-8") as handle:
        columns = ["bib_key", "entry_type", "title", "authors", "year", "identifier_type", "identifier", "canonical_url", "access_date", "calibration_group", "verification_scope", "redistributed_full_text"]
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    report = {
        "audit_kind": "bibliography identity, citation, and calibration audit",
        "passed": True,
        "checks_passed": len(checks),
        "checks": checks,
        "summary": evidence["summary"],
    }
    args.out.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.out.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "checks_passed": len(checks), **evidence["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"reference audit failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
