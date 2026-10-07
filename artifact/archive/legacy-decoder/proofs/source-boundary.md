# Real-source boundary and prior-remedy record

## Inspected source operation

The public OmniServe repository commit `02b2925aa6fa3b92b06316a1524b7f38922cd9c8` contains a per-group W4A8 CUDA kernel at `kernels/csrc/qgemm/w4a8_per_group/gemm_cuda.cu`. In its register-loading path, packed 4-bit weights are separated with low/high-nibble masks such as `0x0F0F0F0F`, each resulting 32-bit word is multiplied by a byte scale, and byte-wise correction is applied with `__vadd4` after broadcasting packed zero-point bytes.

This establishes a real operation-order boundary: ordinary word multiplication can couple sublanes through carries, whereas a later per-byte correction is lane-local. It does **not** establish that the five schemas in this artifact are an exact executable semantics of the CUDA kernel. The kernel also contains data-layout transforms, byte permutations, signed tensor-core inputs, asynchronous copies, shared-memory staging, floating scales, and output epilogues outside the model.

## Relation to the frozen schemas

Mode M captures only the mathematical distinction between a shared packed multiplication and a lane-local correction after extraction. Modes P, W, A, and C are adversarial/control schemas used to test ordering, whole-word correction, signed affine arithmetic, and clipping. The model quantifies over declared interval boxes; it does not reason about all legal CUDA values or instruction-defined overflow.

## Prior practical remedy

LiquidGEMM analyzes W4A8 dequantization overhead and presents an overflow-safe IMAD--XOR construction together with GPU-kernel and end-to-end serving evaluation. That work removes any defensible claim that this project discovered the practical hazard or supplied the first efficient remedy. QServe itself also explains the relevant operation-order/cross-lane issue.

## Consequence for the research claim

The source pattern is real, but the project has neither a production importer nor a new practical implementation. Exact closed forms decide the entire frozen grammar without carry-state search. The correct final claim is therefore a bounded mathematical characterization and a negative formulation result, not a production checker, kernel optimization, or new validation architecture.

## Stable references

- QServe paper record: MLSys 2025, “QServe: W4A8KV4 Quantization and System Co-design for Efficient LLM Serving.”
- OmniServe repository and inspected commit: `https://github.com/mit-han-lab/omniserve/tree/02b2925aa6fa3b92b06316a1524b7f38922cd9c8`.
- LiquidGEMM: SC 2025, DOI `10.1145/3712285.3759852`.

Only citation, source inspection, and an independently written mathematical abstraction are integrated. No external source file is copied into this artifact.
