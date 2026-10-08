# CPU-native realization

`native_bridge.cpp` implements the paper's finite accumulator traversal in
C++17 and the packed decoder's whole-word and lane-wise execution in unsigned
32-bit arithmetic. `bridge.py` binds declared inputs, compiles, and compares
native outputs against the existing certificate schema and arbitrary-precision
Python reference paths. No CUDA source is imported or executed by this bridge.
The original artifact license applies; external source licenses are unchanged.

## Correspondence to the model

The native accumulator state is exactly `(T,E,B,F)`. `p053_convert` implements
the signed wrapping/saturating conversion; `p053_advance` reconstructs the
previous lowered value using the **previous** accumulator declaration, applies
the current term and accumulator conversions, and updates the sticky failure
flag and first failed observation. This includes initial conversion, width
changes, intermediate observations, and final-observation suppression.

`prepare(...,true)` groups mathematical products and retains the first declared
pair and all member indices. `walk` retains every layer, every edge, and the
lexicographically least full prefix for every state. Its native JSON certificate
uses `bptc-exact-accumulator-certificate-v1` unchanged. No format-version change
or reinterpretation of old measurements is involved.

The matched baseline uses `prepare(...,false)` and the **same** `walk`, state
representation, sorting, allocation, edge storage, and witness representation.
It traverses every original operand pair. Both arms precompute mathematical
products; this deliberately gives the baseline the same product-hoisting
opportunity and isolates grouping, rather than comparing against repeated
per-edge multiplication. It is not the old Python implementation's runtime.

`p053_packed` performs one unsigned whole-word multiplication followed by
lane-local modular corrections. `p053_lane_reference` performs lane-wise
multiplication and identical correction. The native carry envelope admits this
packed lowering only on certified-safe boxes. Unsafe boxes remain concrete
correctness controls, not claimed equivalent optimizations.

## Bounds and evidence

The bridge is a finite native subset, not an implementation of arbitrary-size
integer arithmetic. Products and all extrema of exact target prefixes must fit
signed 64-bit integers. These extrema are checked using compiler-supported
128-bit arithmetic before traversal. Aggregate assignment/product-sequence
counts must also fit signed 64-bit; otherwise the bridge fails rather than
emitting a wrapped metric. Widths remain 2--32, schedules 1--64 stages, domains
1--4096 unique pairs, and decoder lanes 1--4 with the original nibble/byte bounds.
The actual predeclared panel is far within these limits. Frontier states and
edges have additional explicit operational caps. These are native applicability
and resource restrictions, not new assumptions of the original proofs.

The checked build uses `-O0 -g -ftrapv`; the release build uses `-O3 -DNDEBUG`.
Both builds execute the same bounded conformance inputs. Exact native JSON
equality between these builds is a check, not a proof of the compiler.
The harness compares the original 64 complete native quotient certificates
with retained certificates, replays all native certificates with the separately
coded checker, checks every baseline edge with a reference transition, and
checks every retained concrete native I/O trace. The three overflow controls
are rejected before output creation.

The retained CPU experiment is separate in `../results/native-cpu/`; fresh
outputs use the caller-selected reproduction path.
The original 64-case edge counts, 5,576 accumulator words, 30 decoder
configurations, and 5,120 fully enumerated decoder words are not replaced or
augmented in the original result directories. Additional native controls are
reported separately: eight signed-boundary cases, six 4/8/16-stage
unique/duplicate-product controls, and one no-observation control.

## Entry points

The harness defaults to `artifact/results/native-reproduction`. An explicit
`--out` selects a different new output directory, including a private directory.
Compiler caches and temporary files are confined to that output directory.
Supply a Zig compiler with `--zig`, or put `zig` on PATH. The harness does not
download or install a toolchain. It defaults to native x86-64 Windows or Linux
targets; `--target` records an explicit override. Compilation and execution
must use a runnable target for the current host.

```sh
# Run from artifact/; Zig must already be installed or supplied explicitly.
python native/bridge.py prepare
# For a separate output location and compiler:
python native/bridge.py prepare --out <new-output-directory> --zig <zig-executable>
```

`prepare` is correctness-only. It never invokes the measurement mode. It refuses
to replace a completed conformance record. Compiler version, commands, native
assembly, optimized/checked outputs, input panel, comparisons, bounds, and
functional source/binary hashes are retained. Those hashes bind later
measurements to the conformance-checked executable and input panel.

The measurement entry point is `python native/bridge.py measure --out <output>
--slot <run-identifier>`. It uses 21 alternating-order paired runs
with 16 executions per timed arm and 16 untimed traversal/decoder warmups.
Emission and fused arms have no separate warmup calls. It reports traversal
plus full in-memory evidence construction separately from product preparation
and JSON serialization. The separate Python replay checker is outside the
native traversal timing. The prepare+walk ratio is a sum of separately timed
phases, **not** a timed fused end-to-end path. It excludes serialization and
Python checking. `checker_cost.py --slot <assigned-slot>` measures replay
after the native job finishes, using 21 samples per case and its own 200,000-unit
cap; its timed calls include the semantic-work ledger's bookkeeping. Run
measurement jobs serially. Before warmups or timing, the native
process selects the lowest currently permitted logical CPU, sets its affinity,
and verifies the actual one-bit mask. On Linux this is the executing thread's
affinity; the native program is single-threaded. The original and actual masks
are saved in raw conformance/measurement output. Failure to pin or verify
aborts execution. The checker is pinned to the same CPU and records its mask.
Actual machine paths and a serial reservation protocol belong in the caller's
execution report, not these source files.
Every raw pair and every slower case must be retained.
Only local CPU-native performance on this synthetic panel can be claimed.

## Retained local measurements

The measured host is an Intel Core i7-12700KF, Windows 11 Pro 10.0.28000 x64,
with Zig 0.15.2/Clang 20.1.2 and the native target/flags above. Native and
checker processes both verified CPU 0, actual mask `0x1`; the native original
allowed mask was `0xfffff`. Frequencies and thermal conditions were not fixed.
There are 2,037 retained native pairs (79 accumulator cases and 18 safe decoder
boxes, 21 pairs each) and 1,659 separate checker samples. No pairs are filtered.

Ratios are baseline/optimized times. The original 64 accumulator cases have
per-case median walker ratios 1.483--1.979. Their preparation+walk component-sum
ratios are 1.346--1.598. The unique-product controls retain the negative results:

| Control | Walker ratio | Separately timed prep.+walk ratio |
| --- | ---: | ---: |
| 4 stages, unique products | 1.001 | 0.953 |
| 8 stages, unique products | 1.002 | 0.971 |
| 16 stages, unique products | 1.000 | 0.985 |

Three preparation+walk medians favor the baseline; no walker median is below one.
These near-unity walker medians are observations, not significance claims.
The 18 certified-safe decoder boxes have median paired ratios 1.075--1.080;
each timed call uses 1,024 deterministic in-bounds words from a periodic
sequence. Every timed box repeats: tiny boxes contain four distinct words;
full and alternating boxes contain sixteen. Both arms use warm memory and
one function call per word. This is not representative input-distribution
coverage. The 12 unsafe boxes are retained correctness controls, not timed
as equivalent optimizations. This is a packed decoder example, not a serving
kernel benchmark.

Preparation+walk is `median((P_U + W_U)/(P_Q + W_Q))`, with all four component
times measured separately in each pair. It is not a fused timed end-to-end
path. Walk includes full in-memory graph and witness construction, not only
arithmetic. Full-certificate emission uses buffer appends and `std::to_chars`;
the same field traversal supplies an ostream comparator. Both serialize to
identical bytes on all 79 cases. Frozen-graph serialization includes per-call
buffer/stream allocation and string materialization, excluding disk I/O.
Original-case buffered/stream paired speedups span 29.02--39.09. A separate
fused prepare--quotient-walk--serialize comparison improves by 19.91--26.55;
both arms use the same quotient algorithm. Buffered serialization/walk ratios
span 2.7--5.2. Separate Python checker medians span 106.3--323.6 us.
There is no measured full-workflow baseline/quotient speedup,
and the walker ratios must not be described as that result.

The public evidence retains one complete `native-conformance.json.gz`
(including all native I/O traces), the checked/release equality and reference
comparison record, all native/checker raw samples, the executed protocol,
environment, and compiler-generated function excerpts. Full private build
outputs and assembly are preserved separately, not duplicated in the package.
`provenance.json` binds the compressed and uncompressed output, each data file,
the exact native/harness/checker/reference sources, and the 94 original
certificates. No compiler executable, PDB, cache or machine command is included.

From `artifact/`, inspect the retained evidence without compiling or timing:

```sh
python native/report.py --results-dir results/native-cpu --check
```

`report.py` recomputes all per-case sample statistics and the three native TeX
inputs, verifies the functional bindings, and reads gzip directly. It does not
run scientific transitions or performance jobs. Actual commands with host
paths remain in the private execution report. The sources and interface above
support a fresh caller-owned run, but the retained measurements establish only
this Windows CPU execution, not tested portability to every target.

The current Python implementation has its own correctness receipt in
`../evidence/current-accumulator-correctness.json`. The measured provenance and
raw samples remain bound to the kernels used for measurement.
`data/measured_context.zip` contains those two kernels and the three generated
TeX inputs. It supplies a self-contained measurement context; no private
repository or historical Git checkout is required. From the artifact root,
choose a new destination outside the project:

```sh
python -B native/materialize_measured_context.py --out /tmp/decoder-measured-context
python -B native/current_correctness.py --historical-project /tmp/decoder-measured-context
```

The verifier runs the measurement report check in that context, verifies the
unchanged native and evidence bindings, and compares complete retained native
certificates, baseline edges and concrete traces with the current Python
implementation. The receipt covers correctness against retained evidence;
it does not measure the current Python checker's runtime.

Artifact-root CI materializes this context from the supplied fixture. It then
uses `prepare_current_context.py` to supply the three generated inputs to the
current verification layout. The finite-campaign and native-conformance jobs
are unchanged. Run the seven copy-admission regressions separately with
`python -B tests/context_regression.py`.

## Proof and implementation mapping

| Paper/proof obligation | Native realization | Check |
| --- | --- | --- |
| Finite conversions and initialization | `p053_convert`, layer zero, concrete initialization | signed-boundary controls, full traces |
| Target--error normal form | `p053_advance`, `State` | every layer/state equals existing certificate |
| Product transition congruence | `prepare` plus shared `p053_advance` | complete class/member tables and baseline edges |
| Exact reachability | `walk`, full layers and edges | independent certificate replay |
| Least prefix/global counterexample | ordered state map and prefix comparison | all state witnesses, decisions, concrete oracle |
| Failure-history/first-failure preservation | sticky `bad`/`first` update | intermediate-observation and no-observation controls |
| `sum |R_i||P_i|` versus `sum |R_i||D_i|` | explicit native edge counters | original totals 416 and 1,016 |
| Packed carry theorem | envelope plus `p053_packed` | safe/unsafe declared boxes and concrete outputs |
| Lane-local bijective correction | separate byte correction after multiplication | independently reconstructed word outputs |

The handwritten arguments remain in `../proofs/exact-accumulator-certificates.md`
and `../proofs/packed-decoder-closed-form.md`. Native conformance does not
mechanize those proofs, validate the frozen CUDA block's memory/control
assumptions, or establish GPU, production, whole-kernel, or deployment results.
