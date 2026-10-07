# Local CPU-native evidence

These are the actual separate native records for the declared synthetic P053
panel, not replacements for `../publication/`. One Intel Core i7-12700KF,
Windows 11 Pro 10.0.28000 x64, Zig 0.15.2/Clang 20.1.2, and verified CPU-0
affinity `0x1` were used. See `environment.json` and `protocol.json` for flags,
pairing, phase definitions, and uncontrolled-frequency limits.

| File | Role |
| --- | --- |
| `panel.json` | Complete predeclared 79 accumulator and 30 decoder declarations |
| `native-conformance.json.gz` | One lossless complete native output: certificates, baseline layers/edges, and concrete I/O traces |
| `comparison.json` | Reference comparison totals and all 79 per-case checks |
| `raw-samples.json` | All 2,037 native pairs, original timer bytes unchanged |
| `checker-samples.json` | All 1,659 separate Python replay samples and semantic-work charges; executable path reduced to basename |
| `measurement-summary.json`, `checker-summary.json` | Original per-case sample summaries |
| `analysis.json` | Recomputed medians, all slower cases, and phase/overhead definitions |
| `assembly-excerpts.txt` | Four compiler-generated arithmetic function excerpts; debug/path directives omitted, not a standalone assembly unit |
| `environment.json`, `protocol.json` | Real host, compiler and affinity plus the executed predeclared protocol; no machine commands |
| `provenance.json` | Consumed hashes/byte counts binding evidence, complete decompressed output, exact scientific sources and 94 retained certificates |

The checked and optimized complete native outputs are equal. Only one is
published; both original outputs and full assembly are preserved privately.
No binaries, PDBs, compiler cache or private commands are included here.
Functional schemas, including `bptc-exact-accumulator-certificate-v1`, remain
unchanged. Gzip is read directly by the checker below and can be decompressed
with any standard gzip utility.

From the artifact directory, validate these retained statistics and bindings:

```sh
python native/report.py --results-dir results/native-cpu --check
```

This recomputes all 97 timed-case medians from all samples, checks source/data
bindings and the three native generated TeX inputs, and does not compile, run
semantic transitions, or measure anything. Hashes bind lineage/integrity; they
are not compiler proofs or independent peer review.

The matched accumulator baseline uses the same walker and evidence storage,
traversing every pair instead of each distinct product. Both precompute
products. Ratios are baseline/optimized; original accumulator walker medians
span 1.469--1.977 and preparation+walk component-sum medians 1.325--1.587.
Unique-product controls preserve two slower walker cases and three slower
component-sum cases. All raw slower pairs and outliers remain present.

Preparation+walk is the median of `(P_U+W_U)/(P_Q+W_Q)` from **separately
timed phases**, not a timed fused end-to-end path. It includes neither JSON
serialization nor Python checking. Quotient serialization on a frozen graph
and separate Python replay costs can dominate the walker; baseline serialization
and the full checking workflow are not timed. There is no whole-checker speedup
claim. Decoder timings cover only the 18 certified-safe boxes, using 1,024
deterministic in-bounds words per call, and yield
1.077--1.079. The 12 unsafe boxes remain correctness controls.

All timed decoder sequences are periodic: tiny boxes have four distinct
words and full/alternating boxes sixteen. Both arms reuse warm memory and
make one function call per word. These batches do not represent a deployment
input distribution or broad randomized decoder workload.

The result establishes only this local CPU-native verification/decoder example,
not GPU speedup, production representativeness, deployment benefit, or
whole-kernel correctness. `../../native/README.md` maps code and data to proofs
and supplies portable fresh-conformance commands using Zig from `--zig` or PATH.
