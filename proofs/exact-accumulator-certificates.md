# Exact quotient certificates for mixed-width accumulators

## 1. Model

A schedule contains stages `i = 0,...,n-1`.  Stage `i` declares an ordered,
finite operand-pair domain `D_i`, a signed term conversion `Q_i`, a signed
accumulator conversion `A_i`, and an observation bit.  Each conversion is
either two's-complement wrap or signed saturation at its declared width.  For
an operand pair `d=(x,y)`, let `p(d)=x*y` be its mathematical integer product.
The reference target is

```
T_0 = initial
T_{i+1} = T_i + p(d_i).
```

The lowered execution is

```
L_0 = A_0(initial)
L_{i+1} = A_i(L_i + Q_i(p(d_i))).
```

At an observed stage, the required equality is
`L_{i+1} = A_i(T_{i+1})`.  Observation history matters: a later numerical
reconvergence does not erase an earlier observed mismatch.

The certificate state after stage `i` is

```
(T_i, E_i, B_i, F_i),
E_i = L_i - A_{i-1}(T_i),
```

where `B_i` records whether an observation has failed and `F_i` is the first
failing stage (or `-1`).  At layer zero the first stage's accumulator
conversion supplies the normal form.  Because `L_i` is reconstructed exactly
from `T_i`, `E_i`, and the previous stage declaration, this is a lossless
normal form rather than an interval abstraction.

## 2. Product quotient

For each stage define `d ~ d'` iff `p(d)=p(d')`.  A quotient class is labelled
by its product and stores the first member in the declared domain order as its
canonical representative.

### Lemma 1 (transition factorization)

For a fixed incoming state and stage, two operand pairs in the same product
class produce the same successor state and the same observation outcome.

**Proof.** Both the reference update and the lowered update use an operand pair
only through the mathematical product `p(d)`.  All conversions, the error
normalization, and the failure update are deterministic functions of that
product and the incoming state.  Substitution of equal products therefore
gives equal successors.  QED.

### Theorem 1 (exact reachable layers)

The producer's quotient layer after every stage is exactly the image of all
concrete prefixes under the target/error state map.

**Proof.** At layer zero both sets contain the single initial state.  Assume
the statement for layer `i`.  Every concrete successor chooses a pair from
`D_i`; Lemma 1 maps it to the successor produced by that pair's quotient
class, so it appears in the quotient layer.  Conversely, every quotient edge
stores an actual representative pair from `D_i`; appending it to a concrete
prefix witnessing the predecessor produces the quotient successor.  Thus the
sets are equal.  Induction completes the proof.  QED.

### Corollary 1 (sound and complete universal decision)

The schedule is equivalent at all declared observations iff no final
reachable state has its failure bit set.

This follows because Theorem 1 preserves every concrete observation history,
not merely final values.

## 3. Least counterexamples

Concrete words are ordered lexicographically by the declared index of each
stage's operand pair.  Within every product class, the first member is the
least concrete member.  The producer retains the least witness reaching each
state.

### Lemma 2 (least witness per state)

At every layer, the stored witness is the lexicographically least concrete
prefix reaching that state.

**Proof.** The empty prefix is least at layer zero.  For a successor, replacing
any selected pair by the first member of its product class preserves the
state by Lemma 1 and cannot increase the word.  By the induction hypothesis,
the least predecessor witness is stored.  The producer forms all canonical
predecessor/class extensions and takes their lexicographic minimum, which is
therefore the least concrete prefix reaching the successor.  QED.

### Theorem 2 (global least counterexample)

If the schedule is inequivalent, the least stored witness among final failing
states is the lexicographically least concrete failing word.

**Proof.** Every failing concrete word reaches a final failing state by
Theorem 1.  Lemma 2 stores a witness no larger than that word for the same
state.  Taking the minimum over all failing states is therefore no larger than
any failing word, and the selected witness itself is concrete and failing.
QED.

## 4. Replay checker

The checker does not call the producer's conversion or transition functions.
It reparses the schedule, rebuilds product partitions, independently
reimplements wrap and saturation, enumerates every quotient edge, reconstructs
the exact state set and least witness map, and compares all serialized layers,
edges, decisions, and counterexamples.

### Theorem 3 (checker acceptance)

If the checker accepts a well-formed certificate, its reachable layers,
universal decision, and reported least counterexample equal those defined by
the schedule semantics.

**Proof.** Acceptance requires exact equality with the independently rebuilt
initial state and each inductively rebuilt successor layer.  The checker then
recomputes the failure decision and least witness from the final layer.
Theorems 1 and 2 connect those reconstructed objects to the concrete
semantics.  QED.

The theorem is about the specified finite language.  It is not a proof of the
Python runtime, JSON parser, or arbitrary CUDA/C++ programs.

## 5. Complexity

Let `R_i` be the reachable quotient state set after stage `i`, `D_i` the
concrete pair domain, and `P_i` its distinct-product set.  The producer and
checker perform

```
  sum_i |R_i| |P_i|
```

semantic transitions, compared with `sum_i |R_i| |D_i|` for an unquotiented
frontier traversal and `product_i |D_i|` for complete concrete enumeration.
The quotient is exact even when it gives no reduction; reduction depends on
product multiplicity and state merging.

## 6. Baseline facts

The no-overflow guard checks that every exact term and every exact prefix
interval fits its declared width.  When it accepts, every conversion is the
identity, so it is sound.  It is incomplete for final-only observations:
with a four-bit saturating accumulator, products `+8,-28` yield reference and
lowered final value `-8` even though the first stage saturates.

The final-range guard checks only the final exact target interval.  It is
unsound: with a four-bit saturating accumulator, products `+8,-8` have final
exact target zero, but the lowered path is `7,-1`, so the final values differ.
These controls separate the need for an exact trace analysis from a merely
conservative range check or a final-range test.
