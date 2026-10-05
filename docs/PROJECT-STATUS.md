# Current manuscript and artifact status

**Current work:** Exact Quotient Certificates for Packed-Integer Decoders and
Mixed-Width Accumulators. The two active folders are `paper/` and `artifact/`.
The README, manuscript, generated inputs and current results all describe this
same finite-semantics study. The earlier five-mode decoder exploration is
archived, not mixed into current quantitative claims.

## What was actually repaired

Earlier inherited archives lacked the quantitative TeX inputs and publication
results required by its main source; its README described a different report.
The current evidence was regenerated in this repair, not recovered from an
unseen prior run. The corrected suite has 30 decoder configurations and 64
accumulator schedules. The impossible requirement of three distinct factor
pairs for products +1 and -1 was removed. The exporter now takes certified
final-state counts from the decision and checks them against replay/direct
state results. The supplied PDFs are newly compiled from these corrected files.

Strict consumer-side validation rejects empty or duplicate domains, invalid
integer widths/types, unknown modes, non-Boolean observations, malformed
layers/edges/witnesses, wrong metrics, wrong state counts and extra layers.
The no-overflow guard includes the initial conversion. Pure final-range and
term-fit/final-range are separate baselines. Complete token equality replaces
permissive regex matching in the source boundary. The citation mapping for
CompCert is corrected, along with identified author/DOI/page errors. Complexity
text accounts for full materialized witnesses and does not claim adjacent-layer
memory for the implemented producer.

These changes were tested; initial failed tests remain in the engineering
record rather than being converted into retrospective successes. The current
unit regression report records 39 executed methods, zero failures,
zero errors and no skipped tests. This is an internal self-audit, not an
independent or blind external review.

## Evidence that supports the current paper

Each retained run contains 64 accumulator certificates, 30 decoder certificates,
64 concrete oracle records, 64 quotient-free direct-state records, 20 decoder
oracle records, two CSV tables and detailed mutation outcomes. In total 246
scientific files match byte-for-byte between main and reproduction. Labels and
CPU/RSS measurements are intentionally run-specific. The actual finite results
are 16 equivalent and 48 inequivalent accumulator schedules; 18 equivalent and
12 inequivalent decoder configurations. The concrete oracles cover 5,576 and
5,120 full words respectively. All implemented applicable paths agree on
verdict and least counterexample. The active experiment does not contain 104
plans, a trillion-input stress test, a second source anchor, a general CUDA
frontend or a new SMT benchmark.

The retained main/reproduction charges are 26,888 each. The cumulative repair
ledger at this snapshot records 187881 of 200000
declared units, including preliminary attempts and rechecks. The ledger is the
current numerical authority and is carried through final checks. Its units
are semantic obligations, not hardware instructions. The historical campaign
already exceeded its original cap (lower bound 209,282); no fresh budget
retroactively repairs the whole-project violation.

## Further executed validation repairs

The additional saved-result audit reproduced two defects in the inherited
validator: coordinated alteration of a baseline verdict and its summary was
accepted during semantic replay, and duplicate JSON members were accepted.
These are validation defects, not counterexamples to the arithmetic theorem.
The input loader now rejects duplicate members and non-finite JSON values.
Case-table columns, oracle count/type fields and provenance bindings are
checked exactly. Replay independently recomputes all three interval guards
from the declared domain rather than trusting the saved baseline booleans.

Eight new regressions bring the executed suite to 39 methods. The repaired
validator replayed both complete retained runs and recomputed their baselines,
charging 15,370 obligations. The 246 scientific files still agree byte for byte.
The actual pre-fix acceptance and post-fix rejection evidence is retained in
`results/reverification/`. No new larger workload or kernel performance
experiment was invented. A final clean-extraction test/build is recorded there
separately; it does not claim a new execution of the full campaign.

## Reference and citation checks

All 68 retained entries are actually cited: 67 scholarly papers/books and one
software source. Each has a recorded primary-source identity, stated purpose
and access scope in `evidence/reference-reverification.json` and `evidence/reference-audit.json`; actual source context is
in `evidence/citation-context.tsv`. Author, title, DOI and article/page errors
found in the supplied records were corrected. In particular, the earlier
Boolector entry used an unrelated CAV DOI, the SWAR entry used an incorrect
Springer DOI/page range, and several bylines were incomplete or wrong.

This recheck corrected the formal MLSys AWQ title to include "On-Device"
and removed an erroneous LNCS series field from the JSAT Boolector article.
Optional arXiv classification fields were removed rather than retaining
unverified labels. The reference checker binds each current BibTeX record to
the exact reviewed record; three negative controls reject title drift, author
drift and the CompCert-to-QServe macro error.

The MIX-PC coauthor page and retained journal metadata disagree on the year
and the last two authors' order. The current entry follows the retained journal
metadata and remains explicitly qualified pending the full version-of-record
byline. Seven entries were checked only in partial indexed primary records.
All 68 have source and purpose records, but this is not a claim that every field
of every entry has independent full-text confirmation.

A resolving URL alone is not a truth certificate. Some publisher full texts
were inaccessible, and metadata conventions differ for Boolector's 2014/2015
record and the release/copyright year of Hacker's Delight. The chosen record
and qualification are preserved. No claim is made that all cited full papers
were read, all cited experiments were replicated, or the 12/5/5 full-text
calibration requirement was satisfied. Offline citation checks do not
independently re-fetch publisher metadata.

## Scientific scope and limitations

The decoder envelope follows a narrow carry bound; the accumulator proof uses
a standard exact finite-state quotient and least-prefix argument. This study
provides explicit contracts and a checked finite implementation, but it has
not established a new general verification principle, a significant TACO-level
contribution, a broad kernel workload benefit, or superiority to strong general
validators. Agreement on selected examples and a long bibliography cannot
supply that missing scientific significance argument.

No proof assistant, independent peer review, arbitrary frontend, memory or
concurrency model, floating epilogue, GPU benchmark or model-quality experiment
is included. Cases were developed within the same project, not independently
preregistered. Several deliberately contain repeated products, so the observed
edge reduction must not be represented as typical production compression.
These are substantive research limits, not just pending submission forms.

The current paper has 16 content pages plus four reference pages; the supplement
has six pages. The original internal exactly-20-content-page target is not met,
and no padding or class/margin/font alteration was used to force it. Live TACO
author-guideline and ACM authorship-policy fetches returned 403; the supplied
class/style are unchanged, but current external submission compliance is not
certified. Substantive AI assistance is disclosed; human authorship and
accountability decisions have not been made by this artifact.

## How to read the final checks

`results/reverification/package-check.json` is a file/evidence consistency check, not a scientific
approval gate. `results/reverification/repaired-semantic-replay.json` records actual semantic replay of saved
certificates and comparison of the two complete runs. The final clean-extraction
records, when present, record execution from an extracted candidate package.
The PDF audit records actual pages, fonts and errors examined. None of these
can justify a promise of 100 percent correctness, originality or acceptance.
