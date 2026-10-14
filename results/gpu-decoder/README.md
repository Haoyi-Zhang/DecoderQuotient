# GPU decoder arithmetic

`study.json` and `device-outputs.bin.gz` contain actual CUDA Driver API execution
on a GeForce GTX 1050 Ti, with the recorded driver, OS, CPU and Python environment.
Two PTX arms realize the same four-byte input/correction contract: whole-word
multiply with byte correction, and independent lane multiply with byte correction.

All 660,480 words in the 30 original decoder boxes were executed by both arms.
The compressed binary stores each case's little-endian packed outputs followed
by its lane outputs; offsets and lengths are in the JSON. All 18 equivalent
domains agree, and the 12 inequivalent domains reproduce exact least witnesses.
The portable consumer reconstructs both complete arithmetic outputs and all
certificate decisions without loading CUDA. Acceptance checks the retained
data and measurement protocol, not the honesty of an external operator or the
correctness of a GPU compiler by proof.

Timing covers only the 18 certificate-admitted boxes, two batch sizes, one
warmup per arm and 15 alternating-order pairs per case/batch. All 540 pairs
remain, with 72 warmup launches and 1,080 timed launches. The conformance panel
adds 60 launches. In total, these launches check 41,428,992 output words;
660,480 unique declared inputs are distinct from repeated timing inputs.
The separate certificate replay ledger contains 4,165 schema/transition units.
Neither that counter nor the historical host campaign's ledger is a count of
all GPU instructions, word comparisons or project-development work.

Each device allocation is bounded to 65,538 words. Stores use an output offset
with checked guards on both ends. Host transfer-call intervals include input
copy, output poisoning, arguments/events/launch, completion and full output
copy. They exclude input admission, host-array preparation and reference
comparison. Event intervals cover one launch on the default stream, including
scheduling and possible host enqueue gaps; they are not isolated instruction
latency. Both arms use identical buffers, 128-thread blocks and output checks.
Device/setup and certificate-replay costs are reported separately; driver
caches were not purged. This display GPU was shared, without locked clocks or
pinned host affinity. Case medians show near aggregate parity, not a stable
hardware or serving speedup.

From the artifact root:

```sh
python -B native/gpu_decoder_study.py check --out results/gpu-decoder
python -B -O -m unittest tests.test_gpu_decoder_consumer
python -B native/gpu_decoder_report.py --results-dir results/gpu-decoder --paper-dir ../paper --check
```

To run fresh actual-device measurements on an available compute-capability
6.1-or-later CUDA device, use a new destination:

```sh
python -B native/gpu_decoder_study.py run --out <new-results-directory>
```

The run command requires the real driver/device and fails if unavailable.
Portable CI consumes these saved records and exercises corrupt-record controls;
it does not claim to rerun a GPU on hosted CPU runners. The PTX is an arithmetic
realization, not the original CUDA frontend, load/layout/MMA kernel or QServe
serving workload. Original publication and CPU evidence retain their own
sources, schemas, timing definitions and measurements.
