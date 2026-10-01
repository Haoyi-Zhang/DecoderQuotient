# Scope of the resource counter

The original `enumeration_charge` is a **partial counter**, not a certificate that the complete campaign obeyed its enumeration ceiling. It counts carry transitions, exhaustive small-word valuations, packing checks, selected mutation replay transitions, SMT queries and interpreter replays. The analytical control counts complete closed-form decision calls. The scalar ablation's per-code loop was not charged. This omission was found during delivery inspection, after the retained scientific runs.

This cannot be fixed by relabeling the old number. The legacy cumulative charge is 155,450, including a conservative 77,240 charge for an unsuccessful invocation whose terminal accounting assertion occurred after the full case loop. Under the conservative interpretation that a scalar code-value check is an enumerated check, a sufficient lower bound is already **209,282**, above 200,000:

```
14,840 intake checks
62,222 retained primary charged units
    97 focused charged units
 1,051 closed-form decision calls
65,536 scalar value checks for case-126 in the first completed case loop
65,536 scalar value checks for case-126 in the retained case loop
-------
209,282 lower bound
```

The two scalar terms each follow from 4,096 logical coordinates times 16 code values. This case uses 8-bit lanes, multiplier 2 and zero point 8, so every scalar reference is in [-16,14] and the ablation cannot return early. The first case loop belongs to the unsuccessful invocation: its failure was the later aggregate-accounting assertion, not an early scientific test failure. This lower bound omits all other scalar checks and all non-scalar work in that unsuccessful invocation. It is not an exact total and is not an instruction count for the SMT solver.

The finite results already retained have not been erased, and the historical full campaign cannot be made compliant retroactively. Scientific execution remained stopped until a new atomic pre-execution budget and conservative trace meter were installed. A separate confirmatory campaign then re-executed only the focused boundary checks and closed-form comparison. Its integration pilots and final hard-metered runs total 36,880 of 200,000 conservative events and exactly match the retained focused and closed-form outputs. See `reproduced-clean/combined-budget.json`. This bounded confirmation does not reproduce the historical 142-case producer/checker/SMT/oracle campaign. Any positive reformulation or full-campaign rerun requires a new question, complete prospective accounting model, and fresh allowance.

The standalone README describes how a reader could reproduce the finite results, but those commands were **not executed from a clean extraction** in this campaign. No successful clean scientific reproduction is claimed. The maximum recorded primary RSS and CPU timings remain valid measurements for their named invocations; they do not repair the enumeration defect.
