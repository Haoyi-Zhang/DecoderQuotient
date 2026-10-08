# Exact Quotient Certificates for Packed-Integer Decoders and Mixed-Width Accumulators

This artifact implements finite-semantics certificates and their CPU-native
realization. Finite results are in `results/publication/`; CPU measurements
are in `results/native-cpu/`. The manuscript sources are provided separately
in the project delivery's `paper/` directory.

## What is implemented

`bptc/packed_decoder.py` produces and replays byte-lane decoder certificates.
`bptc/exact_accumulator.py` produces product-quotient target/error certificates;
`accumulator_checker.py` independently validates declarations, states, edges,
minimal witnesses, decisions and metrics. `accumulator_oracle.py` enumerates
concrete words. `direct_state.py` traverses all operand pairs without quotienting.
The last three arithmetic routes do not invoke certificate production.
Within each accumulator layer, the producer and separately coded checker now
reuse a state's previous-width lowered value and each class's converted term.
These are fresh invocation-local values, first prepared after the unchanged
edge charge. Every original class edge, ordered layer/witness, diagnostic and
semantic obligation remains; this does not reduce the scientific edge counts
or establish a runtime improvement. `tests/hoisting_regression.py` supplies a
separate concrete-prefix enumerator and is an explicit CI step in addition to
the unchanged 47-method discovery suite.
The source check is complete frozen-token equality, ignoring only comments and
whitespace; it is not a general CUDA importer.

`native/native_bridge.cpp` is the C++17 realization of the same accumulator
and packed decoder semantics. `native/bridge.py` compiles and checks it against
the retained certificates, separately coded replay and concrete reference
paths. Its matched baseline uses the same full native graph/witness walker
without product grouping; both arms precompute products. Accepted exact
products, target prefixes and counts must fit signed 64 bits, checked using
128-bit arithmetic before traversal. It does not import or execute CUDA.

The active code requires Python >=3.11 and only the standard library. The
campaign command requires Linux/POSIX `resource` support to impose its 120-second
CPU and 2.5-GiB address-space limits; it fails before semantic execution when
these limits cannot be installed. Semantic functions can be imported on other
hosts under caller-owned resource bounds, with unavailable POSIX RSS recorded
as null, not zero. No GPU, external model, private data or network service is
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

## Separate CPU-native evidence

The original publication evidence and its schema are unchanged. The native
panel adds 15 clearly named controls to the 64 original accumulators and checks
all 30 decoders. Optimized and checked builds agree on complete native output;
all original accumulator certificates match, including 416/1,016 edges and
5,576 concrete words. Three oversized-product/prefix controls fail before
semantic traversal and output creation.

One Intel Core i7-12700KF Windows host, Zig 0.15.2/Clang 20.1.2, and verified
CPU-0 affinity `0x1` produced 2,037 native paired samples and 1,659 separate
checker samples. Original accumulator per-case median walker ratios are
1.483--1.979 and preparation+walk component-sum ratios are 1.346--1.598.
The latter adds **separately timed phases**, not a timed end-to-end path,
and excludes JSON serialization and Python checking. Three unique-product
controls are slower for preparation+walk. All raw slower
pairs and outliers remain in the records. The 18 safe decoder examples measure
1.075--1.080 against lane-wise native evaluation; unsafe boxes are not timed.

Buffered integer JSON preserves complete certificate bytes while improving
emission by 29.02--39.09 over ostream on original cases. The matched fused
prepare--walk--serialize call improves by 19.91--26.55, with the same quotient
in both arms. Serialization/walk median ratios span 2.7--5.2; separate Python
replay medians span 106.3--323.6 us. There is no measured whole-checker speedup, GPU
performance, or production/deployment benefit. See `native/README.md` for the
complete baseline, phase definitions, bounds, negative controls, and proof/code
mapping.

Public `results/native-cpu/` contains all raw timing samples, compact summaries,
a single functional gzip of the complete native output, source/data bindings,
and small compiler-function excerpts. Private compiler binaries, PDBs,
caches, commands and absolute host paths are not published. The retained
statistics and source bindings are checked in the measured context described
below, not by substituting changed sources into that historical measurement.

Saved timings are bound to the measured sources. The supplied
`data/measured_context.zip` restores those inputs in a separate directory, so
the public artifact does not require access to a private Git revision. The
current correctness receipt is `evidence/current-accumulator-correctness.json`.
Run from this artifact directory and choose a new destination:

```sh
python -B tests/hoisting_regression.py
python -B native/materialize_measured_context.py --out <new-context-directory>
python -B native/current_correctness.py --historical-project <new-context-directory>
```

The restored context contains the measured `artifact/` inputs and generated
`paper/` tables. The current verifier runs the
unchanged historical `report.py --check`, retains every source/data/statistic/
TeX gate, binds current sources separately, then compares current complete
producer packets and independent replay against all retained native layers,
edges and concrete I/O traces. It also reruns the literal regressions. This is
current Python conformance to retained evidence, not fresh native execution,
a timing rerun, a new campaign, or a GPU/deployment result. `--emit` prints a
receipt without writing files. Current checker runtime remains unmeasured.

For fresh bounded correctness only, supply an already available Zig compiler:

```sh
python native/bridge.py prepare
# Or: python native/bridge.py prepare --zig <zig-executable> --out <new-directory>
```

The default output is `results/native-reproduction`; no private path is
hardcoded. Preparation never starts performance measurements. Timing remains
a separate caller-authorized serial operation.

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
The runner discovers all 47 current tests, including the continuing-ledger CLI
controls, rather than loading only one test module. Tests include schema,
initialization, minimum-witness, extra-layer, source-token, budget-atomicity,
missing-file, new-output-tampering, canonical JSON byte, reproduction-path and
retained source-attribution cases.
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
from the project root. See `../paper/README.md` for TeX dependencies and the
separate native saved-data check and current build information.

## Budget and interpretation

The retained historical main and reproduction commands each charged 26,888 obligations,
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

## Historical re-verification records

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

The retained continuing repair ledger after those clean-extraction regressions is
187,881 / 200,000 declared units. The earlier full saved-result semantic replay
used 15,370 units; the clean-extraction unit suite used 1,653. Those retained
PDFs were rebuilt from that extraction and matched the then-reviewed PDFs
byte for byte. That extraction did not re-run the full scientific campaign.

## Automated scientific checks

The standalone artifact repository's `scientific-checks.yml` regenerates two
finite runs, replays their certificates and interval baselines, compares their
246 scientific files with each other and the retained evidence, and runs all
discovered regressions. The Ubuntu 24.04 job bounds the complete command block
to 240 seconds of wall time, applies per-process CPU/address-space/file limits,
retains failure exit codes, and uploads raw outputs even when a gate fails.
It does not build the sibling paper or establish mathematical correctness from
test agreement. Adding the workflow is not evidence that a remote run occurred.
