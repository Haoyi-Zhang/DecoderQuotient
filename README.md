# Exact Quotient Certificates for Packed-Integer Decoders and Mixed-Width Accumulators

This artifact implements finite-semantics certificates, CPU-native realization,
and a CUDA-driver realization of decoder arithmetic. Finite results are in
`results/publication/`; CPU measurements are in `results/native-cpu/`, and GPU
decoder records are in `results/gpu-decoder/`. Manuscript sources are provided separately
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
without product grouping; both arms precompute products. The initial value
and both operand components must fit signed 64 bits. Products, target-prefix
extrema, assignment counts and product-sequence counts must also fit signed
64 bits; these are checked with 128-bit arithmetic before traversal or output
staging. Walk-time count checks remain in place.
It does not import or execute CUDA.

The active arithmetic code requires Python >=3.11 and only the standard library. The
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
replay medians span 106.3--323.6 us. These CPU component records do not measure
the complete checker or a GPU. See `native/README.md` for the
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
python -B native/bridge.py prepare --zig <zig-executable> --out <new-native-directory>
python -B native/current_correctness.py --historical-project <new-context-directory> --native-results <new-native-directory>
```

The restored context contains the measured `artifact/` inputs and generated
`paper/` tables. The current verifier checks the unchanged historical
`report.py --check` gates, then runs both freshly compiled native executables,
their complete conformance and admission controls. It compares complete
producer packets, independent replay, layers, edges and concrete I/O traces,
with separate bindings for current source and historical measurements. It
also reruns the literal regressions. `--emit` prints a functional receipt
without writing files. No timing or GPU/deployment experiment runs in this
procedure. A separate current complete-call experiment is described below;
it does not reinterpret historical checker timings.

For fresh bounded correctness only, supply an already available Zig compiler:

```sh
python native/bridge.py prepare
# Or: python native/bridge.py prepare --zig <zig-executable> --out <new-directory>
```

The default output is `results/native-reproduction`; no private path is
hardcoded. Preparation never starts performance measurements. Timing remains
a separate caller-authorized serial operation.

## Complete same-contract workflow

`results/workflow-cost/` compares identity pair branches with product branches
using the same native walker, complete state/witness/edge representation,
serializer, publication mechanism and strict consumer guarantees. The distinct
identity format is `bptc-pair-accumulator-certificate-v1`; its shared metric keys
count identity branches, not distinct products. The proof explains why both
partitions preserve the same least-state witnesses and decision.

All 79 schedules have one warmup per arm and seven alternating-order measured
pairs: 553 pairs, 1,106 timed calls and 158 warmup calls. Complete-call timing
includes ledger construction, native startup/input admission/preparation/full
evidence/serialization/file close/publication, parent wait/read, strict JSON
parsing, declaration binding and full replay. One-off builds, fixture creation,
warmup, logging, statistics and post-call equality are excluded. The original
64 case medians span 0.872--1.211, with median 1.021; 20 favor ordinary pair
traversal. The 4/8/16-stage unique-product controls have ratios
1.037/1.033/0.964. These variable process/file
measurements do not establish stable whole-checker or deployment speedup.

The native parser checks every complete declaration read before validating
its fields. Both optimized and checked native builds reject all proper token
prefixes of a mixed accumulator/decoder regression panel before staging output.
The complete-call record was measured using these current parser sources.

The public scientific record contains 79 exact text inputs, 158 complete
deterministic packet bodies, all raw samples, environment, one-off build costs
and functional bindings. The actual 1,264 outputs (10,150,160 logical bytes)
remain private, including every warmup and slower sample. Historical result
directories and ledgers are unchanged. Physical allocated disk bytes, peak RSS,
energy, hardware counters and representative deployment remain unmeasured.

```sh
python -B -O native/workflow_cost.py --out <fresh-results> --native-dir <prepared-native> --pairs 7
python -B -O native/workflow_cost.py --out results/workflow-cost --check
python -B native/workflow_report.py --results-dir results/workflow-cost --paper-dir ../paper --check
```

The native comparison/admission/reporting consumers use executable conditions,
not removable Python assertions. `tests/test_native_consumer.py` checks wrong
native evidence and incomplete measurements in normal and optimized Python;
`tests/test_pair_replay.py` checks the identity consumer against literal prefixes.
The immutable `data/measured_reporting_sources.json` fixture restores the two
original reporting sources against unchanged measured provenance. It is a
scientific source context, not a fallback verifier or an authorship approval.
The current correctness command launches its historical report with Python
environment options disabled, then checks current native sources separately.

## Check the supplied records (no new semantic execution)

The original command below audits retained records, not new timing.

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
The runner currently discovers 69 tests, including the portable GPU consumer
and continuing-ledger CLI
controls, rather than loading only one test module. Tests include schema,
initialization, minimum-witness, extra-layer, source-token, budget-atomicity,
missing-file, new-output-tampering, canonical JSON byte, reproduction-path and
retained source-attribution cases.
Ten separate citation-comment tests cover the existing generated-macro scope,
active citation contexts and escaped percent signs. Run them with
`python -B -m unittest tools.test_reference_comments` and repeat with `-O`;
scientific CI runs both modes. These parser tests are separate from the
69-method discovery inventory and its semantic-work ledger.
Generic unittest discovery can run them, but the supplied runner additionally
persists the semantic-work charges. An acceptance report cannot replace
reading or independently checking the proof.

## One-package consistency checks

From this directory:

```sh
python -m pip install -r requirements-package.txt
python tools/package_check.py --project-root .. \
  --out results/package-check.json
```

This additionally requires the actual two PDFs, every TeX input and figure,
aligned README titles, the exact current case sets and all citation mappings.
The current edge-count figure check also requires ReportLab, the existing
Python renderer's dependency, declared in `requirements-package.txt` and
installed by the finite-semantics CI job before its explicit package-generation
regressions. It checks the actual CSV, retained evidence and
generated macros, then records the renderer's bar rectangles to verify the
linear zero baseline and heights. It does not rerender a PDF, require TeX fonts,
or establish retained-PDF freshness. Its focused positive/negative controls run
with `python -B tests/package_figure_regression.py`; they are separate from the
arithmetic discovery suite.
Decoder profile display names are explicitly mapped in `tools/generate_paper.py`
to the three declared provenance families; the complete generated-text check
still binds every label and numeric cell. Run
`python -B tests/package_generation_regression.py` for its mutation controls.
The flat artifact CI checkout has no sibling paper, so it tests generation and
the package command's generated-input gate using private table fixtures. The
full package command and figure regressions additionally require the supplied
two-folder project; CI is not described as checking those absent paper files.
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
witness storage can be quadratic even on one-state chains. The separate GPU
study executes the declared decoder arithmetic with matched event and
transfer-call measurements. A general CUDA frontend, floating-point semantics,
representative production benchmark and new general quotient principle remain
separate research obligations.

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
arithmetic tests and result replay do not. `docs/核实结果.md` describes the
scientific evidence and reference-reading scope.

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
It also consumes complete GPU conformance records and exercises strict record
controls under ordinary and optimized Python. It does not rerun hardware
timings on hosted CPU runners, build the sibling paper, or establish
mathematical correctness from test agreement. Remote run status is separate.

## GPU decoder arithmetic

The CUDA driver JIT executes two PTX arms with identical bounded buffers and
byte corrections. Both are checked on all 660,480 words of the 30 declared
decoder boxes, preserving the 18 equivalent and 12 inequivalent decisions and
their least witnesses. The 540 alternating-order pairs retain all slower and
faster observations; aggregate costs are near parity. Full output words,
raw intervals, host/device identity and one-time setup costs are public.
`results/gpu-decoder/README.md` defines the event and transfer-call intervals,
source context, input counts and reproduction commands. Portable CI validates
saved records without requiring CUDA; fresh runs require an actual device.
This connects the selected arithmetic idiom to GPU execution, not to the
surrounding kernel's indexing/MMA or serving performance.
