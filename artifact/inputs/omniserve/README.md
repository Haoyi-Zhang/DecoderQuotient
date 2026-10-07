# Frozen arithmetic source input

`share_to_reg_one_stage_B.cu` contains the selected arithmetic body and the
upstream implementation attribution to Haotian Tang and Shang Yang. The comment
header identifies the excerpt's whitespace normalization; it is not part of
the selected arithmetic token sequence. `provenance.json` records the upstream repository,
immutable commit and file; `LICENSE` is the retained Apache-2.0 text.
The complete token sequence is compared against `bptc/source_anchor.py`'s
fixed sequence, with comments and whitespace as the only ignored content.
The extracted body was inspected against the primary repository source.
This is not compilation or execution of CUDA and does not establish memory,
control-flow, intrinsic implementation, floating-point or concurrency safety.
