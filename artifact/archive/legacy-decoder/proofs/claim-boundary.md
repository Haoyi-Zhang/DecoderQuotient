# Claim boundary and reviewer attack surface

| Potential objection | Evidence or restriction |
|---|---|
| The decoder search is unnecessary. | Agreed and incorporated: an exact linear upper-envelope test replaces search for the source-bound decoder. |
| A no-overflow condition is only sufficient. | The accumulator method is exact for the finite schedule; it represents the lowered error and observation history. |
| Final range is enough. | A four-bit `+8,-8` counterexample is proved and included. |
| Product quotient may lose counterexamples. | Transition factorization, reachability, and least-witness preservation are proved; a concrete oracle checks every evaluation case. |
| Producer and checker share a bug. | The checker independently restates casts and transitions; a separate concrete oracle provides a third implementation on bounded cases. |
| The work is disconnected from real code. | A fixed, licensed OmniServe expression block is imported and structurally checked. |
| The source parser proves the full CUDA kernel. | Explicitly not claimed; its narrow trusted boundary is documented. |
| Results are generated-only and too favorable. | The suite includes safe controls, visible overflow, reconvergence, final-range false accepts, term narrowing, width schedules, observation schedules, and mixed product boxes. |
| Baselines are strawmen. | They are presented only as common sufficient/unsound guards, not as state-of-the-art tools; closest translation-validation and bit-vector systems are compared separately in the paper. |
| Exhaustive testing is called a general proof. | General results are written proofs over the finite language; enumeration is labelled validation of implementations and selected instances. |
| Budget accounting can miss loops. | Every semantic transition, oracle assignment, mutation, and carried pilot/repair event is charged prospectively in one fail-closed ledger. |
| Reproduction may be irreproducible. | A second clean result tree is generated and certificates/tables are compared byte-for-byte; semantic summaries exclude only run labels and resource measurements. |
| Practical GPU performance is absent. | No speedup or deployment claim is made; the contribution is a CPU certificate/checker for a normalized integer fragment. |
