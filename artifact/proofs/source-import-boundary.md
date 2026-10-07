# Frozen source boundary

The source check is a complete token allowlist, not a C++ structural importer.
The lexer consumes the entire selected block. Only whitespace and comments
are discarded; all remaining tokens must equal the fixed expected sequence.
Unknown statements, reordered operations, extra writes, altered masks/shifts,
changed zero selectors and comment-only decoys are rejected.

The retained block is from the immutable OmniServe commit recorded in
inputs/omniserve/provenance.json. Metadata is separate from the code body.
The body was compared to the primary repository token sequence. Apache-2.0
licensing and original attribution are retained.

Acceptance fixes eight nibble relations, four unsigned byte scales, four byte
zero-point selections, eight whole-word multiplies and eight bytewise stores.
The accompanying arithmetic proof assumes valid loads/stores, the intended
__byte_perm and __vadd4 semantics, and no concurrent interference. It does not
establish those assumptions from the surrounding CUDA program. No accumulator
schedule is automatically extracted, and no complete kernel correctness,
aliasing, memory, floating-point or concurrency claim is made.

The 22 targeted source mutations are recorded individually with rejection
results. Token equality rejects other unlisted rewrites too, including some
semantically harmless changes. This is a deliberately narrow scope choice,
not evidence of a general-purpose semantics-preserving source importer.
