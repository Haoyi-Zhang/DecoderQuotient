"""Self-contained comment controls alongside reference_regressions.py."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import reference_check as checker
from tools.bib_records import dump


class ReferenceCommentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.paper, self.artifact = root / "paper", root / "artifact"
        (self.paper / "generated").mkdir(parents=True)
        (self.artifact / "evidence").mkdir(parents=True)
        self.keys = ["compcert", "quarot", "aarch64tv"] + [f"ref{i:02d}" for i in range(57)]
        entries = [dict(type="article", key=key, author="A. Author", title="Reference " + key,
                        year="2024", doi="10.1000/" + key) for key in self.keys]
        current = next(entry for entry in entries if entry["key"] == "quarot")
        current.update(doi="10.52202/079017-3180", url="https://papers.nips.cc/paper_files/paper/2024/hash/b5b939436789f76f08b9d0da5e81af7c-Abstract-Conference.html")
        historical = dict(current, doi="10.5555/3737916.3741096", url="https://example.invalid/historical")
        (self.paper / "references.bib").write_text(dump(entries), encoding="utf-8")
        records = {entry["key"]: dict(bibliographic_record=historical if entry["key"] == "quarot" else entry,
                                     access_scope="fixture metadata only", primary_source="fixture") for entry in entries}
        self.write_json(self.artifact / "evidence/reference-audit.json", {
            "entries": {key: dict(primary_source="fixture", verification="fixture", citation_purpose="context") for key in self.keys}})
        self.write_json(self.artifact / "evidence/reference-reverification.json", {"records": records})
        bindings = {}
        for relative in ("references.bib", "evidence/reference-audit.json", "evidence/reference-reverification.json"):
            path = (self.paper if relative == "references.bib" else self.artifact) / relative
            bindings[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_json(self.artifact / "evidence/current-metadata-followup.json", {
            "schema": "current-bibliographic-identity-followup-v1", "selected_identity_count": 1,
            "full_text_read_complete": False, "citation_entailment_validated": False,
            "source_bindings": bindings, "scope": "synthetic parser regression fixture",
            "records": {"quarot": {
                "historical_bibliographic_record": historical, "current_bibliographic_record": current,
                "changed_fields": ["doi", "url"], "historical_source_reading_not_extended": True,
                "primary_sources": [{"url": "https://example.invalid/fixture", "read_scope": "fixture"}],
                "read_scope": "fixture metadata only"}}})
        self.macros = r"\newcommand{\CiteCompCert}{\cite{compcert}}" + "\n"
        self.text = "\n".join(r"\CiteCompCert" if key == "compcert" else r"\cite{" + key + "}" for key in self.keys) + "\n"

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def check(self, text=None, macros=None):
        (self.paper / "main.tex").write_text(self.text if text is None else text, encoding="utf-8", newline="")
        (self.paper / "generated/citations.tex").write_text(self.macros if macros is None else macros, encoding="utf-8", newline="")
        return checker.check(self.paper, self.artifact)

    def test_baseline_and_existing_supported_commands(self):
        report, rows = self.check()
        self.assertEqual((report["entries"], report["cited_unique"], len(rows)), (60, 60, 60))
        commands = (r"\cite{aarch64tv}", r"\citet{aarch64tv}", r"\citep[see][p.~7]{aarch64tv}",
                    r"\citeauthor{aarch64tv}", r"\citeyear{aarch64tv}")
        for command in commands:
            with self.subTest(command=command):
                report, rows = self.check(self.text.replace(r"\cite{aarch64tv}", command))
                self.assertEqual(report["cited_unique"], 60)
                self.assertEqual(sum(row["key"] == "aarch64tv" for row in rows), 1)

    def test_commented_sole_citation_loses_coverage(self):
        with self.assertRaisesRegex(ValueError, r"uncited or undefined keys: \['aarch64tv'\]"):
            self.check(self.text.replace(r"\cite{aarch64tv}", r"% \cite{aarch64tv}"))

    def test_missing_bib_key_only_in_comment_is_not_collected(self):
        report, rows = self.check(self.text + r"% \cite{missing_from_bib}")
        self.assertEqual(report["missing_keys"], [])
        self.assertEqual({row["key"] for row in rows}, set(self.keys))

    def test_literal_percent_and_backslash_parity(self):
        for count in range(6):
            with self.subTest(backslashes=count):
                text = self.text.replace(r"\cite{aarch64tv}", "\\" * count + r"% \cite{aarch64tv}")
                if count % 2:
                    report, _ = self.check(text)
                    self.assertEqual(report["cited_unique"], 60)
                else:
                    with self.assertRaisesRegex(ValueError, "aarch64tv"):
                        self.check(text)

    def test_commented_macro_override_is_ignored(self):
        report, _ = self.check(macros=self.macros + r"% \newcommand{\CiteCompCert}{\cite{wrong_work}}")
        self.assertEqual(report["status"], "pass")
        with self.assertRaisesRegex(ValueError, "CompCert macro points at the wrong work"):
            self.check(macros="% " + self.macros)

    def test_macro_text_backslash_parity(self):
        override = r"% \newcommand{\CiteCompCert}{\cite{wrong_work}}"
        for count in range(6):
            with self.subTest(backslashes=count):
                macros = self.macros + "\\" * count + override
                if count % 2:
                    with self.assertRaisesRegex(ValueError, "CompCert macro points at the wrong work"):
                        self.check(macros=macros)
                else:
                    report, _ = self.check(macros=macros)
                    self.assertEqual(report["status"], "pass")

    def test_only_existing_generated_macro_file_is_used(self):
        definition = r"\newcommand{\CiteTarget}{\cite{aarch64tv}}"
        text = self.text.replace(r"\cite{aarch64tv}", r"\CiteTarget")
        report, _ = self.check(text, self.macros + definition)
        self.assertEqual(report["status"], "pass")
        (self.paper / "generated/ignored.tex").write_text(definition, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "aarch64tv"):
            self.check(text, self.macros + "% " + definition)

    def test_context_lines_and_sections_use_active_text(self):
        prefix = "% \\section{Hidden}\r\n% \\cite{missing}\r\n\\section{Active}\r\n"
        report, rows = self.check(prefix + self.text.replace(r"\cite{aarch64tv}", r"\% \cite{aarch64tv} % hidden context"))
        target = next(row for row in rows if row["key"] == "aarch64tv")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(target["line"], 6)
        self.assertEqual(target["section"], "Active")
        self.assertNotIn("hidden context", target["paragraph"])
        self.assertNotIn("missing", target["paragraph"])

    def test_line_endings_are_preserved(self):
        self.assertEqual(checker._strip_comments("a% hidden\r\nb% hidden\rc% hidden\n% eof"), "a\r\nb\rc\n")

    def test_existing_raw_nocite_gate_is_unchanged(self):
        with self.assertRaisesRegex(ValueError, "uncited bibliography inclusion"):
            self.check(self.text + r"% \nocite{compcert}")


if __name__ == "__main__":
    unittest.main()
