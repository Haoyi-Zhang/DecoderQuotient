# Exact quotient certificates for packed-integer kernel fragments

This standalone artifact implements the paper's bounded integer language:

- a restricted structural importer for a fixed, licensed OmniServe W4A8
  expression block;
- an exact carry-envelope decision and replayable carry certificate for packed
  byte multiplication;
- an exact target--error/product-quotient certificate for mixed-width signed
  wrap and saturating accumulators;
- an independently implemented checker;
- independent concrete oracles for all accumulator cases and selected decoder
  boxes;
- baseline guards, mutation campaigns, prospective resource accounting, and a
  clean reproduction comparison.

The artifact does **not** verify a complete CUDA kernel.  It does not model
pointer validity, races, synchronization, ldmatrix/MMA, floating-point scale
application, epilogues, model quality, or GPU performance.

## Quick verification

Use Python 3.10 or newer.  The core artifact has no third-party Python package
requirement.

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=.

python -m unittest -v tests.test_publication_core

python tests/publication_acceptance.py \
  --root . \
  --out reproduced/publication-acceptance.json
```

The retained main and reproduction outputs are under
`results/publication/main/` and `results/publication/reproduction/`.  Their
certificates and CSV tables are byte-identical.

To regenerate a fresh two-run campaign with its own prospective ledger:

```sh
python -m bptc.publication_campaign \
  --root . \
  --out reproduced/publication \
  --limit 200000 \
  --pilot-events 14807
```

The `--pilot-events` value reserves the measured pilot obligations before any
new scientific operation.  The retained publication ledger additionally
carries a repair-validation run; see `results/publication/budget.json` and
`results/publication-history/`.

## Result layout

- `bptc/`: producer, independent checker, oracle, importer, cases, and ledger.
- `inputs/omniserve/`: fixed source excerpt, attribution, and Apache-2.0 license.
- `proofs/`: full proof arguments and claim-boundary analysis.
- `results/publication/`: main/reproduction certificates, tables, summaries,
  budget, and final audit.
- `evidence/`: bibliography and source/reference audit material.
- `tests/`: unit and artifact acceptance tests.

## Interpretation

Written proofs establish soundness, completeness, and least-counterexample
preservation for the declared finite language.  Checker acceptance validates a
particular certificate relative to the checker.  Enumeration cross-checks the
listed bounded instances.  The source importer validates only the retained
expression shape.  These are separate claims and must not be collapsed into an
end-to-end kernel guarantee.


<!-- PUBLICATION-HARDENING-BEGIN -->
## Evidence tiers and reviewer-facing audit

The artifact separates five evidence tiers rather than treating every passing
command as a proof: (1) written general arguments in `proofs/`; (2) an exact
certificate producer; (3) independently implemented replay checkers; (4)
finite concrete oracles and mutation controls; and (5) a prospective,
fail-closed obligation ledger.  `evidence/claim-traceability.json` maps each
paper claim to these files.  The retained historical campaign has a
conservative lower bound of **209,282** obligations and is not counted as
resource-compliant evidence against the **200,000** prospective ceiling.

Run the artifact-only audit from this directory:

```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
python -m unittest discover -s tests -p 'test_*.py'
python tests/publication_acceptance.py \
  --root . --out results/publication/publication-acceptance.json
python tests/reviewer_attack_audit.py \
  --root . --out results/publication/reviewer-attack-audit.json
```

When `paper/` and `CURRENT-STATE.md` are present one directory above, pass
`--project-root ..` to include the PDF, page-contract, and disclosure checks.
The audit is fail-closed but is still a self-audit, not independent peer
review and not an acceptance forecast.

## Research-process disclosure and accountability

An interactive generative-AI system materially assisted research design,
implementation and test drafting, proof and counterexample exploration,
experiment orchestration, analysis, and manuscript drafting.  Human authors
must inspect the source, proofs, raw results, citations, and generated paper;
they remain responsible for every claim and for complying with the
then-current venue rules before external use.  This repository does not
present automated assistance as independent review.
<!-- PUBLICATION-HARDENING-END -->
