# Theory status

This document completes the mathematical argument for the frozen five-schema model. Section 8 proves a stronger negative boundary: exact closed forms and binary domain splitting solve the decision and least-witness problems without carry-state search. The certificate proofs remain correct, but they do not support a necessity, novelty, or production-kernel claim. The arguments are paper-and-pencil proofs, not machine-checked general proofs.

# Mathematical specification and proofs

These are paper-and-pencil arguments. The executable checker is not machine-verified. All universal quantifiers below range over the explicitly defined schema, not arbitrary C, LLVM, CUDA or serving kernels.

## 1. Integer and word model

Let b be one of 4, 8, 16 or 32, B=2^b, and L=32/b. A word contains exactly L lanes; a partial word is outside the implemented input language. A code q_i lies in an integer interval D_i=[l_i,u_i] contained in [0,15]. The full domain is the Cartesian product D_0 × ... × D_(L-1). Distinct code coordinates may be chosen independently. The integer parameters satisfy 0≤s≤min(31,B−1) and 0≤z≤15. They are fixed per case, not floating quantization scales or inferred correlations.

Write [x]_B for the Euclidean residue in [0,B−1], and sig_b(d)=d for d<B/2 and d−B otherwise. The reference lane value is r(q)=s(q−z), an unbounded mathematical integer. A decoded lane is correct when its *signed interpretation* equals r(q), not merely when residues agree. Pack(q)=Σ_i q_i B^i, with q_0 the least-significant lane. Whole-word arithmetic is modulo B^L.

Five target decoders are defined:

- M (multiply, then lane subtraction): W=[s Pack(q)]_(B^L); lane i is sig_b([digit_i(W)−sz]_B).
- P (lane subtraction, then multiply): W=[s Σ_i [q_i−z]_B B^i]_(B^L); output sig_b(digit_i(W)).
- W (multiply, then whole-word repeated-residue subtraction): W=[s Pack(q)−[sz]_B Σ_i B^i]_(B^L); output signed digits.
- A (whole-word affine correction): W=[s Pack(q)−sz Σ_i B^i]_(B^L); output signed digits.
- C (independent product clipping): output sig_b([min(sq_i,B/2−1)−sz]_B). This last schema has no shared arithmetic carry.

M is source-inspired. P, W and A are alternative operation-order/correction schemas, not claims about actual source-code implementations. C is a deliberately modeled saturation alternative. Mathematical division in a carry is floor division; no real-number rounding mode, floating epilogue or activation quantizer is modeled.

## 2. Exact carry recurrence

At lane i, incoming carry is c_i, initially zero. In M set t=sq+c_i, c_(i+1)=floor(t/B), and d_i=[t−sz]_B. In P set t=s[q−z]_B+c_i; in W set t=sq−[sz]_B+c_i; in A set t=s(q−z)+c_i. For P,W,A set c_(i+1)=floor(t/B) and d_i=t−B c_(i+1). In C set c_(i+1)=0 and d_i=[min(sq,B/2−1)−sz]_B.

### Lemma 1 (word/recurrence agreement)

For every domain word, the signed digits emitted by the recurrence equal the corresponding whole-word target decoder.

Proof. For P,W,A let v_i denote respectively s[q_i−z]_B, sq_i−[sz]_B, and s(q_i−z). Euclidean division gives v_i+c_i=d_i+B c_(i+1). Multiply by B^i and sum i=0,...,j−1. Interior carry terms telescope, c_0=0, and

Σ_(i<j) v_i B^i = Σ_(i<j) d_i B^i + c_j B^j.

At j=L the last term vanishes modulo B^L, proving that the d_i are exactly the extracted unsigned digits of the specified word. This remains valid for negative v_i and negative carries because the Euclidean remainder is nonnegative; truncation toward zero would not be interchangeable. For M use v_i=sq_i in the identity before the lane-local subtraction. The target then applies the same residue subtraction to each extracted digit, without propagating its borrow. C is immediate from its lane-local definition. Signed interpretation is applied identically on both sides. QED.

The last outgoing carry c_L is discarded. Requiring it to be zero strengthens the contract unnecessarily. For example, take b=8,s=18,z=14, D_0=D_1=D_2={14},D_3={14,15}, and M. Incoming carries are zero; reference digits are 0,0,0,0 or 18. The final product may be 270, generating c_4=1, but extraction and lane subtraction still yield 18. The output is correct.

### Lemma 2 (finite carry bounds)

For s>0, M and P have 0≤c_i≤s−1; W has −1≤c_i≤s−1; A has −s≤c_i≤s−1; C has c_i=0. For s=0 all modes have only carry zero.

Proof. Initial carry zero satisfies every relevant interval. In M and P the multiplicand is in [0,B−1]. If 0≤c≤s−1, then 0≤s operand+c≤sB−1, so floor division yields [0,s−1]. In W subtracting a residue in [0,B−1] and allowing c≥−1 gives t≥−B. Its upper bound is at most s(B−1)+(s−1)=sB−1. In A, q−z lies in [−15,15]. With c in [−s,s−1], −16s≤t≤16s−1. Since B≥16, floor(t/B) lies in [−s,s−1]. C follows by definition. If s=0, the subtractions and products are zero, and induction fixes c=0. QED.

Thus the mathematical number of (carry,bad) states is at most 2s for M/P, 2(s+1) for W, 4s for A, and 2 for C, with a two-state upper bound in the zero-scale case. Actual reachable states can be fewer. The checker guard of 128 states and carries in [−32,32] contains every legal state: s≤31 implies 4s≤124, −s≥−31 and s−1≤30.

## 3. Certificate layers and exact decisions

A state is (c,e), where e is true exactly when some processed lane disagreed with its reference. Start at (0,false). Each legal next q produces the recurrence's next carry and e'=e OR (sig_b(d)≠s(q−z)). A layer is the exact set of reachable states after a fixed number of lanes. With each state the certificate stores the lexicographically minimum input prefix reaching it. The input order compares q_0 first, then q_1, and so on, using the ordinary order 0<...<15. It is not numeric order on the packed word, signed-code order or a search over program lengths.

The checker recomputes all successors from the previous verified layer. It rejects omitted states, extra states, duplicate states, wrong domains, false carries, false bad flags or nonminimum prefix labels. Tables bind to expected local domain sequences; case-level parameters bind to a separately supplied expected specification. A certificate cannot change that specification by changing its own copy.

### Theorem 1 (exact layers and minimum prefixes)

For every position j, replay's accepted layer equals the reachable state set, and each accepted prefix label is the least prefix reaching its state.

Proof. At j=0, the required singleton and empty prefix give both properties. Assume them at j. A concrete j+1-prefix decomposes into a concrete j-prefix and a last code q in D_j. Its j-state occurs in the verified layer by induction. The checker explores that state with q, producing its exact successor; therefore it omits no reachable state. Conversely, each explored successor is reached by the stored concrete prefix extended with a legal q, so it introduces no unreachable state. For a fixed predecessor state and a fixed extension q, replacing any other predecessor prefix by the minimum stored one cannot increase the extended word lexicographically, and does not change the successor. This replacement is valid because the next domain is independent of the prefix. Minimizing all such candidates for a successor therefore gives exactly its minimum prefix. Requiring equality with the supplied next layer proves the induction step. QED.

### Corollary 1 (decoder soundness and bounded completeness)

A legal word schema is universally bit-exact if and only if its final exact layer has no bad state. If a bad state exists, the minimum prefix among final bad states is a concrete failing word and is the lexicographically first failing word of the fixed length.

Proof. Lemma 1 identifies the recurrence with target execution. Theorem 1 enumerates exactly its reachable observations. A bad final state records at least one failed lane; the flag cannot be reset. Conversely, every failed lane sets the flag on that concrete execution, so some final bad state exists. Minimum-prefix exactness yields the claimed order. QED.

This is completeness of the *word decoder schema*, not completeness of all kernel acceptance criteria. The procedure supplies a certificate for either outcome, so rejection of a candidate kernel is compatible with successful validation of its certificate.

### Corollary 2 (work and storage)

For domain sizes d_i and reachable layer sizes K_i, local transitions are T=Σ_(i<L) K_i d_i. Because d_i≤16 and L≤8, the legal carry bounds make this a small finite recurrence. Storing full prefixes incurs O(Σ_j j K_j) scalar entries and constructing/comparing prefixes may incur an additional O(L) factor per transition; a claim of constant-cost prefix handling would be inaccurate. The implementation does not rely on an automaton-minimality theorem.

### Proposition 1 (sharp carry-free guard for M)

Assume every r(q_i) fits signed b bits. In M, the decoder is universally correct if and only if every reachable incoming c_i is zero for i=0,...,L−1; there is no requirement on c_L. Let C_0=0 and C_(i+1)=floor((s u_i+C_i)/B). Then this condition is equivalent to C_i=0 for every observed lane i.

Proof. M emits [s(q_i−z)+c_i]_B. Since r fits signed b bits, equality to r holds exactly when c_i≡0 mod B. Lemma 2 and s<B give 0≤c_i<B, so this means c_i=0. The transition is monotone in q and c, and the domain is a product. Choosing each previous q at its upper endpoint attains each maximum carry C_i inductively. Thus C_i=0 is equivalent to all reachable incoming carries being zero. The final carry is unobserved. QED.

A parallel result for P uses max{[q−z]_B:q∈D_i} rather than u_i. This maximum is not always the upper endpoint q=u_i because modular subtraction is discontinuous at z. The main implementation uses exact tables, avoiding an unjustified endpoint rule. Neither proposition applies without signed representability, to relational domains, or by ignoring combined multiply/subtract borrows in W/A.

## 4. Layout and byte representation

A tensor has n≤4096 elements, rank at most four, and n divisible by L. The flattened layout vector π has length n, is a permutation of 0,...,n−1, and the activation-consumption vector must equal π. Input and output footprints are half-open intervals [I,I+ceil(n/2)) and [O,O+4). Both must lie inside [0,min(M,2^32)); endpoints are computed as mathematical integers, so no host-language address wrap is accepted. The two intervals must be disjoint. This is a declared finite footprint discipline, not an operational model of CUDA addresses or activation buffers.

Packed input extraction is modeled as an exact nibble-to-code map. For a byte x+16y with x,y∈[0,15], masking the low four bits yields x and shifting by four then masking yields y. The 32-code source-inspired interleave stores byte i of word j as q_(4j+i)+16 q_(16+4j+i), for 0≤j,i<4. Extracting low nibbles of the four words, followed by their high nibbles, restores the logical code vector. The identity follows separately for every distinct digit position; it does not require exhaustive enumeration of 16^32 code vectors.

The implemented interpreter receives codes and explicit maps, not actual device memory. The separate interleave helpers and tests substantiate the nibble schema. A general bit-level layout importer and a model of arbitrary overlapping accesses are absent. In particular, an alias-contract failure is not presented as proof of a differing numerical output.

### Lemma 3 (block-table reuse)

Suppose all word tables satisfy Corollary 1 and each physical block refers to a table whose ordered domains equal those of that block under π. Then all decoded physical lanes equal r(q_(π(j))).

Proof. Fix a physical block and an input satisfying the logical domains. Domain binding places its ordered word in the referred table's Cartesian domain. The table's universal equality applies by Corollary 1. Repeat for each finite block. Reusing one table for equal ordered domain sequences changes neither premise nor conclusion. The parameter binding includes width, s,z and mode, so equality of domains alone never authorizes cross-parameter reuse. QED.

## 5. Accumulator observations

Let independent a_i range over one integer interval [a_min,a_max]⊆[−128,127]. For physical step j use p_j=a_(π(j)) s(q_(π(j))−z), and source prefix S_k=Σ_(j<k)p_j. For each term, its exact minimum m_j and maximum M_j are attained among the four endpoint products a*s(q−z). The exact prefix extrema are L_k=Σ m_j and U_k=Σ M_j.

### Lemma 4 (exact source prefix extrema)

These formulas are the true minimum and maximum over the Cartesian input domain.

Proof. A bilinear function on the rectangle of two independent intervals reaches its extrema at corners: fixing one argument yields a linear function of the other, whose extrema occur at endpoints; repeating for the remaining argument yields the four corners. Every term uses a distinct logical index because π is a permutation. Independently choose the two endpoints that attain each term minimum, realizing their sum simultaneously. All other sums are at least this sum. The maximum argument is identical. It is not claimed that every intermediate integer between L_k and U_k is attainable. QED.

The target modular accumulator starts at v_0=0 and updates v_(j+1)=sig_(w_j)([v_j+p_j]_(2^w_j)), where w_j∈{4,8,16,32}. The signed integer v_j is used in the next update, even when the width changes. The saturating variant instead clamps v_j+p_j to [−2^(w_j−1),2^(w_j−1)−1]. Multiplication in these formulas is mathematical, followed by the declared accumulator operation; no separate machine multiply overflow is implied.

For modular arithmetic, checkpoints are all explicit signed observations, the final prefix n, and every prefix k immediately before a widening w_k>w_(k−1). At checkpoint k require [L_k,U_k] to fit signed w_(k−1) bits. The width before the widening is decisive: checking only the wider destination is unsound. Narrowing inserts no extra checkpoint. For saturating arithmetic, every prefix is a checkpoint, defining a no-saturation contract.

### Theorem 2 (modular observation sufficiency)

If all modular checkpoint ranges fit, then every explicit observation and the final target value equal the source prefix at that point.

Proof. Maintain v_k≡S_k mod 2^(w_(k−1)) after each noninitial step. At the first step the update establishes this directly. If the next width is equal or smaller, the modulus 2^w_next divides the previous modulus. Thus the previous congruence survives the change of modulus, and adding the exact p_k preserves it. If the next width is greater, prefix k is a checkpoint. The induction hypothesis gives congruence at the old width, and the range guard places S_k inside the unique signed representative interval at that width. The target v_k lies in the same interval by its definition, so v_k=S_k as integers. Their equality survives widening, after which the next update reestablishes the congruence. At any explicit observation or final checkpoint, the same uniqueness argument converts congruence to integer equality. QED.

### Theorem 3 (saturating-contract sufficiency)

If every source prefix fits the width used at that prefix, saturating target execution equals the reference at every step.

Proof. Initially both are zero. If v_k=S_k and S_(k+1)=S_k+p_k fits the next signed width, clamping leaves that exact value unchanged. Induction establishes the result. QED.

Theorem 3 is not an equivalence characterization. With four-bit accumulators and fixed terms (7,7,−8,−7,−7,7,7,0), the mathematical final sum is 6. The saturated states are (7,7,−1,−8,−8,−1,6,6), also ending at 6, although intermediate source prefixes violate representability. `results/focused.json` independently records this example. Failure of a no-saturation contract must not be called proof of wrong final output.

### Theorem 4 (compositional sufficient contract)

If the finite layout/footprint contract, all bound word decoders, and the selected modular or saturating accumulator contract hold, then the declared final integer result is exactly Σ_i a_i s(q_i−z), for every allowed input.

Proof. Lemma 3 replaces each target decoded lane by its source value. The consumption map equals π, pairing that weight with its correct activation. Theorems 2 or 3 then give the mathematical sum in physical order. Since π is a permutation and mathematical integer addition is commutative and associative, this equals the logical-order reference sum. The footprint contract separately guarantees the stated finite intervals and disjointness; it is not used to infer behavior of unmodeled address-generating instructions. QED.

## 6. Failure reporting and exactness boundaries

The declared order is layout, decoder, accumulation. A valid certificate reports the first false Boolean obligation in this order, or acceptance when all are true. This is least failing *declared stage*, obtained by ordered selection of recomputed facts, not causal fault localization, minimum edit distance or shortest failing execution. Invalid certificates are rejected before their classification is trusted.

Decoder witnesses are complete fixed-length word inputs. An accumulation failure reports an exact out-of-range prefix bound, not necessarily a final mismatch. A layout failure reports a structural contract failure; zero activations, repeated weights or safe overlap under a different execution policy can make a rejected layout numerically harmless. Even decoder equality is stronger than a final dot-product equality if all activations are zero. These examples prevent promoting the component completeness theorem into a whole-kernel completeness claim.

The exact-state induction uses independent future domains. Correlated codes or shared uncertain scales require a richer state that preserves the relevant relation. The prefix bound theorem also relies on distinct terms with independent per-index activation/code choices. Reusing a logical coordinate invalidates its attainability argument. These restrictions are enforced or explicitly excluded rather than hidden in an overclaimed universal theorem.

## 7. Implementation evidence versus proof

Producer and checker encode the same specified recurrence independently; they can share a conceptual error. The whole-word interpreter and direct SMT encoding therefore use different computational representations. The complete small oracles additionally check the minimum witness order by exhaustive tuple enumeration. The 96 alterations exercise selected certificate obligations, not every malformed input. Five focused JSON type alterations ensure that booleans and integers cannot substitute for one another in bound specifications, minimum witnesses or range records. These finite checks do not mechanically establish any theorem above.

All theorems concern deterministic arithmetic, not races, barriers, instruction scheduling, C undefined behavior or real hardware. A fixed 32-bit word width is a mathematical parameter in this language and is not evidence that a particular GPU instruction implements the language.


## 8. Stronger analytical control: closed forms eliminate state search

This result was derived after the frozen comparative campaign, while attacking the need for its state construction. It changes the significance of the formulation: every decoder in the frozen grammar admits an exact linear-time decision without carry-state reachability. It does not invalidate the carry-certificate proof, but prevents presenting state search as necessary for this language.

Let F assert signed representability of every reference lane. For M,P,W,A, the output digit is congruent to r(q_i)+c_i modulo B. Under F, correctness is therefore equivalent to c_i≡0 mod B. Lemma 2 and s<B imply |c_i|<B, so this is c_i=0. The same statement remains true when s=0, whose reachable carry is zero.

At incoming carry zero define g(q)=sq for M; s[q−z]_B for P; sq−[sz]_B for W; and s(q−z) for A. Universal equality is equivalent to F plus 0≤g(q)<B at every nonfinal lane for every local code. Sufficiency is induction: zero carry enters and leaves each nonfinal lane. For necessity, take the earliest nonfinal lane whose zero-carry transition can produce a nonzero carry. Earlier lanes preserve zero on every input. Choose a violating code there and any code in the next nonempty domain. The next signed observation is wrong. The last outgoing carry remains unrestricted.

Consequently the exact additional interval conditions are:

| Mode | Every nonfinal interval [l,u] must satisfy |
|---|---|
| M | s*u < B |
| P | s≤1 or l≥z |
| W | 0≤s*l−[sz]_B and s*u−[sz]_B < B |
| A | s*(l−z)≥0 |

M and W follow from monotone endpoint bounds on g. For A the upper bound already follows from signed representability; only nonnegativity remains. For P, scales zero and one cannot generate a carry. When s≥2 and q<z, put d=z−q>0. Reference fit implies 1≤sd≤B/2. Thus s[q−z]_B=s(B−d)=sB−sd≥sB−B/2≥B. This necessarily carries. When q≥z, g(q)=r(q) is nonnegative and less than B by reference fit. Hence P's test is exact.

For C, first require F. If s=0 all outputs are zero. Otherwise put H=B/2. Codes with sq≤H−1 are exact. A clipped code is exact precisely when sq−(H−1) is divisible by B. The clipped codes in an interval [l,u] form a suffix beginning at h=max(l,floor((H−1)/s)+1). An empty suffix is safe. A one-element suffix is safe exactly when its correction error is divisible by B. A suffix of at least two elements contains adjacent codes whose correction errors differ by s. Since 0<s<B, their errors cannot both be divisible by B, so the domain is not universally exact. This is also a constant number of tests per lane. These arguments finish an exact O(L) decision for every mode.

A minimum failing word also does not require the carry table. Negating the exact universal decision is an exact test for the existence of a failure in any interval product. First check existence. Then fix coordinates in physical lexicographic order. Binary-split the current coordinate's interval and keep the lower half if it admits a failing completion; otherwise keep the upper half. The halves partition the prior nonempty failing domain, so existence is preserved. At a singleton, fix the coordinate and proceed. Each choice is the smallest coordinate admitting a failing completion with the already fixed prefix. The final singleton is consequently the lexicographically first failure. The number of decision calls is at most 1+Σ_i ceil(log2 |D_i|), with O(L) arithmetic work per call.

`bptc/closed_form.py` implements these formulas and binary witness search independently of the producer, checker, whole-word interpreter and SMT encoder. It compares 147 local tables across the retained 142 cases, including minimum witness labels; all agree. The measured control makes 1,051 closed-form decision calls. It is a post-campaign analytical control and not added to the predeclared timing comparison. The theorem is the principal reason not to claim that this bounded grammar demonstrates a need for a novel carry-search mechanism.


## 9. Final formulation consequence

The source operation is grounded in a public W4A8 kernel, but QServe already states the operation-order hazard and LiquidGEMM supplies an overflow-safe practical remedy. Together with Section 8, this falsifies the proposed significance claim for the frozen grammar. The completed result is the exact mathematical boundary itself and the preserved negative evidence. No theorem here establishes CUDA/PTX behavior, floating-point equivalence, workload prevalence, hardware performance, or a general compiler validator.
