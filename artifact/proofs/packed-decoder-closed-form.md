# Packed-byte multiplication: carry certificate and closed form

Let `B=2^b`, digits `x_i` satisfy `0 <= x_i <= u_i`, and
`X=sum_i x_i B^i`.  The lowered idiom multiplies the complete word by an
unsigned scalar `s`, extracts each base-`B` digit, and applies a lane-local
modular addition.  The reference multiplies each digit by `s` independently
and applies the same lane-local addition.

Define carries

```
c_0 = 0,
y_i = (s x_i + c_i) mod B,
c_{i+1} = floor((s x_i + c_i)/B).
```

The reference pre-correction digit is `(s x_i) mod B`.  Modular addition by a
fixed byte is a bijection, so correction neither creates nor hides a mismatch.
Thus lane `i` agrees iff `c_i = 0 (mod B)`.

For the source-anchored parameter boundary, `B=256`, `0<=s<256`, and
`0<=x_i<=15`.  Inductively, `0<=c_i<=15`: if the bound holds at `i`, then
`s x_i+c_i <= 255*15+15 = 15*256`, so `c_{i+1}<=15`.  Hence a lane agrees iff
its incoming carry is exactly zero.

The recurrence is monotone in both the digit and incoming carry.  Therefore
the maximum reachable carry is obtained by choosing every upper bound:

```
C_0 = 0,
C_{i+1} = floor((s u_i + C_i)/256).
```

All words in the box are equivalent iff `C_i=0` for every observed lane
`i`.  Carry beyond the most significant retained lane is irrelevant because
the lowered word is interpreted modulo the word width.  This gives the exact
linear-time universal decision used in the artifact.

The serialized carry layers are also exact: an induction identical to the
accumulator reachability proof shows that enumerating every digit from every
reachable carry produces exactly the concrete carry set.  Retaining the least
prefix per `(carry,bad,first_bad)` state yields the least counterexample under
lexicographic digit order.  The independent checker rebuilds these layers and
compares them with the certificate.  Tiny boxes are additionally exhaustively
enumerated by a separate whole-word interpreter.
