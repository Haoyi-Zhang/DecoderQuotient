# Exact Quotient Certificates for Packed-Integer Decoders and Mixed-Width Accumulators

This is the active artifact for `paper/main.tex` and `paper/main.pdf` in the
one-package delivery. It is a finite-semantics study, not
an externally accepted paper or the previous decoder-only negative report.
The active results are in `results/publication/`. Archived exploration is
segregated in `archive/legacy-decoder/` and is not current evidence.

## What is implemented

`bptc/packed_decoder.py` produces and replays byte-lane decoder certificates.
`bptc/exact_accumulator.py` produces product-quotient target/error certificates;
`accumulator_checker.py` independently validates declarations, states, edges,
minimal witnesses, decisions and metrics. `accumulator_oracle.py` enumerates
concrete words. `direct_state.py` traverses all operand pairs without quotienting.
The last three arithmetic routes do not invoke certificate production.
The source check is complete frozen-token equality, ignoring only comments and
whitespace; it is not a general CUDA importer.

The active code requires Python >=3.11 and only the standard library. It runs
on one CPU process. No GPU, external model, private data or network service is
required. The historical Z3 library is not loaded by current commands.

## Retained evidence

There are 30 decoder cases (18 equal, 12 unequal) and 64 accumulator schedules
(16 equal, 48 unequal). All 5,576 accumulator words and 5,120 words from 20
small decoder boxes are enumerated. The remaining 10 decoder boxes are checked
by exact carry replay but not whole-word enumeration. The quotient-free state
traversal agrees for all 64 accumulator plans. Frontier edges are 1,016 without
the product quotient and 416 with it; this is not a runtime speedup claim.
The three guards are separately reported: no-overflow has 8 false rejections;
pure final-range has 32 false acceptances; term-fit plus final-range has 24.

Main and reproduction each include 64 accumulator certificates, 30 decoder
certificates, 64 concrete-oracle records, 64 direct-state records, 20 decoder
oracle records, two case CSVs, detailed mutation outcomes, summary and per-run
accounting. There are 40 accumulator, 20 decoder and 22 source campaign
mutations. No metadata from the old 142-case campaign is used to fill these
records.

## Check the supplied records (no new semantic execution)

Run from this directory:

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=.
python tools/validate_results.py \
  --results-dir results/publication/main \
  --compare-dir results/publication/reproduction \
  --out results/record-check.json
```

Without `--replay`, this checks record structure, completeness, suite binding,
aggregates, strict JSON/CSV parsing and byte equality, not a new arithmetic proof. It requires the exact
case file sets and rejects missing files even when both sides lack them.

## Fresh regeneration and semantic checking

Use a new output directory; the campaign refuses to overwrite one:

```sh
python -m bptc.publication_campaign \
  --root . --out reproduced/main --label reproduction \
  --ledger reproduced/budget.json
python tools/validate_results.py \
  --results-dir reproduced/main \
  --compare-dir results/publication/main \
  --replay --ledger reproduced/budget.json \
  --out reproduced/validation.json
python tools/run_tests.py \
  --ledger reproduced/budget.json --out reproduced/tests.json
```

With `--replay`, all three baseline guards are also independently recomputed;
a jointly corrupted case table and summary cannot substitute for that check.
Duplicate JSON keys, non-finite values, unexpected CSV columns and modified
source-provenance fields are rejected. Eight additional regressions cover
these boundaries.

The same ledger is carried into every command. A fresh counter describes the
new local reproduction only; it does not reset the historical project budget.
The 39 unit tests include schema, initialization, minimum-witness, extra-layer,
source-token, budget-atomicity, missing-file and new-output-tampering cases.
Generic unittest discovery can run them, but the supplied runner additionally
persists the semantic-work charges. An acceptance report cannot replace
reading or independently checking the proof.

## One-package consistency checks

From this directory:

```sh
python tools/package_check.py --project-root .. \
  --out results/package-check.json
```

This additionally requires the actual two PDFs, every TeX input and figure,
aligned README titles, the exact current case sets and all citation mappings.
It is an offline file/record consistency check, not an online bibliographic
lookup or an independent peer review. The paper builds using `sh paper/build.sh`
from the project root. See `paper/README.md` for TeX dependencies.

## Budget and interpretation

The retained main and reproduction commands each charged 26,888 obligations,
53,776 together. `results/repair-budget.json` also carries failed tests,
preliminary complete runs, saved-certificate replay and final checks. These
counts charge declared units: one concrete oracle word covers its full bounded
trace, not each machine instruction. The ledger is atomic within this
single-process protocol; it is not crash-durable or a multi-process database.

The archived exploration already has a corrected lower bound of 209,282, above
its original 200,000 cap. Bounded repair work does not make the project's entire
history compliant. The current code uses exact integer arithmetic, but its
proofs are handwritten and its state space may grow exponentially. Complete
witness storage can be quadratic even on one-state chains. There is no general
CUDA frontend, floating-point or GPU performance evidence, representative
production benchmark, or established new general quotient principle.

For the current self-audit and unresolved research-readiness limits, read `docs/PROJECT-STATUS.md`. Prior PASS-labelled reports in the inherited input are not treated as evidence that current files exist or that novelty has been established.

## Execution from a clean extracted package

`results/clean-extraction/` is a third regenerated copy from an extracted
candidate ZIP. It is not an additional workload or part of the two-run paper
budget. `results/clean-checks/` preserves the actual campaign, replay, unit-test,
package-check and build logs. Its 246 scientific files match the retained main
run. Both PDFs rebuilt from that extraction are byte-identical to the supplied
PDFs. That earlier clean regeneration consumed budget recorded in the same continuing ledger;
the historical overrun and scientific-readiness limitations remain unchanged.

## Current re-verification records

`results/reverification/repaired-tests.json` reports 39 executed tests.
`repaired-semantic-replay.json` reports replay of both complete retained runs,
independent interval-baseline recomputation and 246 equal scientific files.
`inherited-vulnerability-probes.json` preserves the pre-repair negative results.
The latest clean-extraction test and build comparison are reported separately.
No full campaign was re-run merely to replace unchanged evidence.

The bibliography contains 68 actual references (67 scholarly papers/books and
one software source). `evidence/reference-reverification.json` records each
exact BibTeX record, source, access scope, citation purpose and qualification;
`evidence/citation-context.tsv` contains its actual manuscript context.
Primary records/abstracts and partial indexed records are distinguished;
no all-full-text or 100-percent-accuracy claim is made. From this directory:

```sh
python tools/reference_check.py --paper-dir ../paper \
  --out results/reverification/references.json \
  --contexts evidence/citation-context.tsv
python -m tools.reference_regressions --paper-dir ../paper \
  --out results/reverification/reference-controls.json
```

These two commands require the sibling `paper/` because they inspect citations;
arithmetic tests and result replay do not. See `docs/核实结果.md` for the Chinese
summary of completed repairs and substantive remaining research limitations.

The continuing repair ledger after the latest clean-extraction regressions is
187,881 / 200,000 declared units. The earlier full saved-result semantic replay
used 15,370 units; the clean-extraction unit suite used 1,653. The current
PDFs were rebuilt from that extraction and matched the visually reviewed PDFs
byte for byte. The fresh extraction did not re-run the full scientific campaign.
