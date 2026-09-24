# Source import boundary

The artifact retains a fixed Apache-2.0 excerpt from the OmniServe W4A8
per-group kernel at repository commit
`02b2925aa6fa3b92b06316a1524b7f38922cd9c8`, path
`kernels/csrc/qgemm/w4a8_per_group/gemm_cuda.cu`.

The importer is intentionally narrower than a C++ or CUDA frontend.  It checks
all of the following structural facts in the frozen block:

1. eight named low/high nibble extractions from the four components of a
   `uint4`, with the expected masks and shift;
2. eight whole-word unsigned multiplications;
3. the expected pairing of two extracted words with each of four scalar
   bytes; and
4. eight bytewise `__vadd4` corrections with the corresponding zero-point
   byte.

The parser rejects changes to masks, shifts, source components, product
pairings, destinations, or correction pairings.  A deterministic mutation
suite exercises these failure modes.

This establishes a reviewable syntactic import certificate for the restricted
expression idiom.  It does **not** establish CUDA memory safety, pointer
alignment, race freedom, synchronization, `ldmatrix` or `mma` semantics,
integer intrinsic semantics outside the normalized block, floating-point
scale application, epilogue behavior, or end-to-end QServe/OmniServe
correctness.  Those items remain explicit trusted or excluded boundaries.
