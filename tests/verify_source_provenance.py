#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,urllib.request
from pathlib import Path
COMMIT='02b2925aa6fa3b92b06316a1524b7f38922cd9c8'
REPO='mit-han-lab/omniserve'
SOURCE_PATH='kernels/csrc/qgemm/w4a8_per_group/gemm_cuda.cu'

def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'bptc-source-audit/1.0'})
 with urllib.request.urlopen(req,timeout=60) as r:return r.read().decode('utf-8')

def norm(s): return '\n'.join(line.rstrip() for line in s.replace('\r\n','\n').split('\n')).strip()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--out',required=True);a=ap.parse_args()
 root=Path(a.root)
 local=(root/'inputs/omniserve/share_to_reg_one_stage_B.cu').read_text()
 upstream_url=f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{SOURCE_PATH}'
 upstream=fetch(upstream_url)
 contained=norm(local) in norm(upstream)
 if not contained:
  raise SystemExit('frozen source excerpt is not an exact normalized substring of immutable upstream source')
 lic_url=f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/LICENSE'
 upstream_lic=fetch(lic_url)
 local_lic=(root/'inputs/omniserve/LICENSE').read_text()
 # Some distributions normalize whitespace; compare the full legal text after line-ending normalization.
 license_match=norm(local_lic)==norm(upstream_lic)
 if not license_match: raise SystemExit('frozen upstream license differs from immutable upstream license')
 readme=(root/'inputs/omniserve/README.md').read_text()
 for token in (REPO,COMMIT,SOURCE_PATH,'Apache'):
  if token not in readme: raise SystemExit('missing provenance token in README: '+token)
 out={'status':'PASS','retrieved_utc':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
      'repository':REPO,'commit':COMMIT,'path':SOURCE_PATH,'upstream_url':upstream_url,
      'excerpt_exact_normalized_substring':contained,'license_exact_normalized_match':license_match,
      'local_excerpt_lines':len(local.splitlines()),'upstream_source_lines':len(upstream.splitlines()),
      'scope':'Narrow source excerpt only; no claim of whole-kernel or compiled-binary validation.'}
 Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
