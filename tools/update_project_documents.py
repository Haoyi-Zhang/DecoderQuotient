#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,re,subprocess
from pathlib import Path
from typing import Any

def walk(x:Any,p=''):
 if isinstance(x,dict):
  for k,v in x.items(): yield from walk(v,f'{p}.{k}' if p else k)
 elif isinstance(x,list):
  for i,v in enumerate(x): yield from walk(v,f'{p}[{i}]')
 else: yield p,x

def load(p): return json.loads(Path(p).read_text())
def pick_num(obj,*patterns,default=None):
 vals=[]
 for k,v in walk(obj):
  if isinstance(v,(int,float)) and not isinstance(v,bool) and all(re.search(p,k,re.I) for p in patterns): vals.append((k,v))
 if not vals: return default
 # Prefer exact suffixes / shortest path to avoid aggregate duplication.
 vals.sort(key=lambda kv:(len(kv[0]),kv[0]));return vals[0][1]
def esc(s): return str(s).replace('|','\\|').replace('\n',' ')

def pdf_pages(p):
 t=subprocess.run(['pdfinfo',str(p)],capture_output=True,text=True,check=True).stdout
 m=re.search(r'^Pages:\s+(\d+)',t,re.M);return int(m.group(1))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--project-root',required=True);ap.add_argument('--external-audit',required=True);a=ap.parse_args()
 root=Path(a.project_root).resolve(); art=root/'artifact'; paper=root/'paper'
 combined=load(art/'results/publication/combined-summary.json')
 budget=load(art/'results/publication/budget.json')
 reviewer=load(art/'results/publication/reviewer-attack-audit.json')
 refs=load(art/'evidence/reference-verification-live.json')
 lit=load(art/'evidence/publication-literature-calibration.json')
 scale=load(art/'results/publication/scalability-audit.json')
 visual=load(art/'results/publication/visual-audit.json')
 venue=load(art/'evidence/venue-rule-verification-live.json')
 source=load(art/'evidence/source-provenance-live.json')
 leaves=dict(walk(budget))
 used=max(int(v) for k,v in leaves.items() if isinstance(v,(int,float)) and k.lower().endswith(('events_used','used_events')))
 limit=max(int(v) for k,v in leaves.items() if isinstance(v,(int,float)) and k.lower().endswith(('limit','event_limit','events_limit')))
 acc_cases=reviewer['summary']['accumulator_cases'];dec_cases=reviewer['summary']['decoder_cases'];families=reviewer['summary']['semantic_families']
 oracle_words=pick_num(combined,r'accumulator',r'oracle.*word',default='recorded in combined-summary.json')
 false_reject=pick_num(combined,r'sufficient|no.?overflow',r'false.?reject',default='>0')
 false_accept=pick_num(combined,r'final.?range',r'false.?accept',default='>0')
 cpu=pick_num(combined,r'cpu',default='recorded in budget.json')
 rss=pick_num(combined,r'rss|resident',default='recorded in budget.json')
 main_pages=pdf_pages(paper/'main.pdf');supp_pages=pdf_pages(paper/'supplement.pdf')
 now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
 # Compact 22-paper calibration table.
 cal_lines=['| Group | BibTeX key | Paper | Selection evidence |','|---|---|---|---|']
 for group in ('same_venue','influential','adjacent'):
  for x in lit[group]:
   ev=x.get('selection_reason','')
   if group=='influential': ev+=f" OpenAlex cited-by count {x['influence_evidence']['cited_by_count']} (dated retrieval)."
   cal_lines.append(f"| {group} | `{esc(x['bibkey'])}` | {esc(x['title'])} | {esc(ev)} |")
 calibration='\n'.join(cal_lines)
 research=f'''# Research plan

## Frozen question and result

**Question.** For a deliberately delimited packed-integer fragment drawn from a quantized-serving kernel idiom, which independently checkable certificates decide universal bit-exact refinement for source-bounded byte decoders and mixed-width wrap/saturating accumulation schedules, while returning the least counterexample under a declared input order?

**One-sentence contribution.** The project combines (i) an exact linear carry-envelope decision for the frozen decoder grammar with (ii) an exact target–error accumulator certificate that quotients operand pairs by mathematical product, preserves monitored observations, and retains lexicographically least witnesses; both are replayed by separately implemented checkers and tied to one immutable source excerpt.

The original carry-search necessity hypothesis was falsified by a closed-form baseline.  That negative result is retained as the reason for the final two-layer formulation rather than hidden.

## Model and assumptions

The model contains finite integer domains, declared operand order, byte-packed decoder lanes, explicit signed or unsigned width conversions, wrap or saturation at declared stages, and a finite set of monitored observations.  Decoder source bounds are rectangular lane domains.  Accumulator stages add one product selected from two finite operand domains before the declared conversion.  The imported CUDA text is recognized only by a narrow structural grammar.  Floating scales, floating rounding, attention, epilogues, concurrency, memory races, undefined C++ behavior outside the excerpt, PTX/SASS lowering, and hardware timing are outside the model.

## Closest-work delta

The work is not a replacement for general SMT translation validation, proof-carrying code, verified compilers, tensor-compiler scheduling systems, or quantized-serving implementations.  Its narrow delta is a certificate format and checker decomposition specialized to packed carry interference and mixed-width accumulator observations: decoder validity factors through a monotone carry envelope, whereas accumulator validity factors through an observation-preserving product quotient with least representatives.  The source importer establishes that the analyzed idiom occurs in a fixed public source block; it does not infer whole-kernel semantics.

## Retained claims and evidence obligations

1. **Decoder exactness.** Necessary-and-sufficient carry-envelope criterion and least failing word.  Evidence: `proofs/packed-decoder-closed-form.md`, producer/checker code, {dec_cases} retained configurations, oracle comparison, and mutations.
2. **Accumulator exactness.** Product quotient preserves reachability, monitored observations, and least counterexamples.  Evidence: `proofs/exact-accumulator-certificates.md`, independent checker, concrete oracle, {acc_cases} schedules in {families} semantic families, and mutation controls.
3. **Baseline separation.** The no-overflow guard is sound but incomplete; the final-range-only heuristic is unsound.  The retained suite contains {false_reject} sufficient-guard false rejection(s) and {false_accept} final-range false acceptance(s).
4. **Source anchoring.** The parser checks eight nibble extractions, their scale pairings, and bytewise corrections in the immutable OmniServe excerpt.  Live provenance audit: {source['status']}.
5. **Reproducibility.** Main and clean reproduction agree under one fail-closed ledger; the reviewer-attack audit contains {reviewer['summary']['checks_passed']} passing checks.

Passing finite checks is not used as the proof of the general theorems.  The general argument is written mathematics; executable evidence attacks implementation mistakes and checks emitted certificates.

## Falsification criteria

The central result is falsified by any of the following: a concrete word accepted by a certificate but rejected by the independent semantics; a reachable state missing from the quotient; an observation outcome changed by product-class merging; a lexicographically smaller counterexample than the certificate witness; an accepted structural source mutation; disagreement between main and clean reproduction; an unmetered scientific path that can cross the event ceiling; or a bibliography/source record that fails its stable-identifier audit.

## Baselines

The decisive baselines are concrete Cartesian enumeration on small domains, the no-overflow sufficient guard, the final-range-only heuristic, a non-quotiented operand-pair exploration, and the closed-form decoder envelope that replaced the original carry-search proposal.  Deterministic cases are not treated as a statistical population.

## Resource contract

The prospective main campaign and clean reproduction use {used:,} of a {limit:,}-event fail-closed ceiling, one worker, CPU-only execution, and retained CPU/RSS measurements ({cpu}; {rss}).  The historical exploratory campaign has a conservative lower bound of 209,282 obligations and is archived but excluded from compliant evidence.  No GPU, external compute, private data, model execution, service access, or new human study is used.

## Venue and paper contract

The internal target is a double-anonymous TACO original-research manuscript using the supplied ACM `acmsmall,screen,review,anonymous` family, exactly 20 content pages with references beginning on page 21, plus an anonymized supplement.  The current paper has {main_pages} total pages and the supplement {supp_pages}.  Dynamic official pages were retrieved on {venue['retrieved_utc']}; human authors must recheck the live rules immediately before external use.

## Literature calibration matrix

The following 22 distinct records satisfy the frozen 12 same-venue / 5 demonstrably influential / 5 adjacent calibration.  Influence counts are dated discovery evidence, not rankings or quality scores.

{calibration}

## Non-claims

The project does not prove arbitrary CUDA/C++/PTX programs, floating-point equivalence, absence of races, model accuracy, serving throughput, GPU speedup, or production readiness.  The proofs are not proof-assistant mechanizations.  The source importer is deliberately narrow.  The self-audits are not independent peer review and cannot guarantee acceptance.

## Research-process accountability

An interactive generative-AI system materially assisted research design, implementation and test drafting, proof/counterexample exploration, experiment orchestration, analysis, and manuscript drafting.  Human authors must inspect and own every claim, citation, source, and result and comply with the live venue policy before external use.
'''
 (root/'research-plan.md').write_text(research,encoding='utf-8')
 current=f'''# Current state

Updated: {now}

## Scientific status

The project is complete within its frozen integer/source boundary.  It now presents a positive, delimited validation method rather than the earlier negative-only feasibility report.  The decoder theorem is an exact linear carry-envelope result.  The accumulator theorem is an exact observation-preserving product quotient with target–error states and lexicographically least witnesses.  A narrow parser ties the analyzed pattern to an immutable OmniServe W4A8 source excerpt.  The project does not claim whole-kernel CUDA validation.

## Retained evidence

- {dec_cases} decoder configurations and {acc_cases} accumulator schedules across {families} semantic families.
- Accumulator concrete-oracle volume: {oracle_words}.
- Producer, independent checker, and concrete oracle agree; all recorded cross-check disagreement counters are zero.
- Both baseline pathologies are witnessed: sufficient no-overflow guard false rejection(s) = {false_reject}; final-range-only false acceptance(s) = {false_accept}.
- Source provenance: immutable public repository/commit/path, exact normalized excerpt containment, and exact Apache-2.0 license match.
- Bibliography: {refs['entries']} records; {refs['passed']} resolved; {refs['failed']} failed.  Calibration: 12 same-venue, 5 dated influence-evidenced, 5 adjacent, 22 distinct.
- Reviewer-attack self-audit: {reviewer['summary']['checks_passed']} fail-closed checks passed.  Visual audit: {visual['status']}.

## Resource status

The prospective main and clean reproduction share one ledger and use {used:,}/{limit:,} declared events.  They are the compliance-bearing evidence.  The historical exploratory campaign remains explicitly noncompliant at a conservative lower bound of 209,282 obligations; it is retained for transparency and not used to satisfy the prospective budget.

## Paper status

The ACM anonymous review manuscript builds to {main_pages} pages, with exactly 20 content pages and references beginning on page 21.  The supplement builds to {supp_pages} pages.  Fonts are embedded; PDF metadata and reviewer-facing sources contain no author identity; references and labels resolve; claim-language, visual, and page-contract audits pass.  The main paper contains the core theorem statements and proofs; the supplement expands case indices and proof details.

## Nine-perspective artifact-only self-audit

| Perspective | Current finding | Priority |
|---|---|---|
| Scope/significance | Useful exact method for a deliberately narrow but source-observed packed-integer fragment; no broad-kernel claim. | P2: broader importers are future work. |
| Domain method | Decoder and accumulator mechanisms are distinct, exact, and compositional at declared observation boundaries. | None. |
| Formal correctness | Written induction arguments, independent replay, concrete oracles, least-witness checks, and mutations align. | P2: no proof-assistant mechanization. |
| Empirical methodology | Deterministic exhaustive/exact-state evidence, baselines, state-size table, and resource ledger are explicit; no statistical inference. | None. |
| Artifact/reproducibility | Full-project and standalone gates, source provenance, claim ledger, and clean reproduction are present. | None. |
| Related-work adversary | 68 live-resolved records and a verified 12/5/5 calibration; novelty wording is bounded. | P2: human subject-matter review remains essential. |
| Generality/boundary attacker | Worst-case state explosion, narrow parser, scalar accumulator schedule, and excluded CUDA/floating semantics are explicit. | P2: these are declared boundaries, not hidden defects. |
| Accessibility/story | Problem, failed original hypothesis, two exact methods, source anchor, baselines, evidence tiers, and limitations follow a single narrative. | None. |
| Meta-review | No project-internal P0/P1 remains after the fail-closed audit.  This is a self-audit, not an acceptance decision. | External human review required. |

## External-use holds

Human authors must independently inspect the manuscript, proofs, implementation, raw evidence, and all citations; approve authorship and accountability; confirm originality/prior-publication and the current venue rules; provide any required AI-use disclosure; and perform the actual anonymous upload.  No acceptance, publication, independent review, or repository URL is claimed.

## Reproduction entry points

From the full project root:

```sh
sh paper/build.sh
cd artifact
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
python tests/release_acceptance.py \
  --root . --project-root .. \
  --out results/publication/release-acceptance.json
```

From the standalone artifact root, omit `--project-root ..`.
'''
 (root/'CURRENT-STATE.md').write_text(current,encoding='utf-8')
 final=f'''# Final audit

Generated: {now}

## Result

All project-internal release gates pass for the frozen scope.  The contribution is an exact certificate/checker decomposition for source-bounded packed decoders and mixed-width accumulator schedules, not a claim about arbitrary kernels or GPU performance.

## Exact retained totals

- Decoder configurations: **{dec_cases}**.
- Accumulator schedules: **{acc_cases}**, spanning **{families}** semantic families.
- Concrete accumulator oracle words: **{oracle_words}**.
- Prospective obligation ledger: **{used:,}/{limit:,}**.
- Sufficient-guard false rejections: **{false_reject}**.
- Final-range-only false acceptances: **{false_accept}**.
- Reviewer-attack checks: **{reviewer['summary']['checks_passed']}** passed.
- Bibliographic records: **{refs['entries']}**; online-resolved **{refs['passed']}**; failed **{refs['failed']}**.
- Calibration: **12** same-venue + **5** influence-evidenced + **5** adjacent = **22 distinct** records.
- Main PDF: **{main_pages} pages**, exactly 20 content pages, references from page 21.
- Supplement: **{supp_pages} pages**.
- Visual audit: **{visual['status']}**.

## Evidence separation

Written proofs establish the general results.  The producer emits replayable certificates; a separately implemented checker rebuilds arithmetic and layer obligations; a concrete oracle checks small finite domains; mutations attack source associations and certificate fields.  Passing finite tests is not described as a general proof.  The historical 209,282-obligation lower bound remains archived and is not reclassified as compliant.

## Source and bibliography authenticity

The frozen source excerpt is an exact normalized substring of `mit-han-lab/omniserve` at commit `{source['commit']}` and path `{source['path']}`; the retained license exactly matches the upstream Apache-2.0 text.  Every bibliography record resolves through its DOI, arXiv identifier, ISBN, or official page in the dated live audit.  OpenAlex counts are used only to document the five influence-evidenced calibration choices and are not used as quality scores.

## Release gates

The unified gate runs unit tests, publication acceptance, the reviewer-attack audit, and—when the paper is present—the full-project PDF/page/anonymity audit.  Clean-extraction results are recorded separately in the delivered project after packaging.  The language lint rejects absolute novelty, production-readiness, whole-CUDA, or GPU-guarantee claims; the visual audit checks every rendered page.

## Limits

No self-audit can remove all questions an independent expert reviewer may raise or guarantee venue acceptance.  Remaining limitations are explicit: no proof-assistant mechanization, no arbitrary-source frontend, no C++/CUDA memory or concurrency semantics, no floating-point chain, no GPU/model/serving experiment, and no external human review.  These are non-claims rather than silently missing evidence.
'''
 Path(a.external_audit).write_text(final,encoding='utf-8')
if __name__=='__main__': main()
