#!/usr/bin/env python3
"""Unified, offline release gate for the artifact or full project."""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path

def run(cmd,cwd,env):
 p=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True)
 if p.returncode:
  raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
 return p.stdout

def readpass(path):
 d=json.loads(Path(path).read_text())
 if d.get('status') not in {'PASS','pass'}: raise SystemExit(f'non-PASS report {path}: {d}')
 return d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--project-root');ap.add_argument('--out',required=True);a=ap.parse_args()
 root=Path(a.root).resolve(); project=Path(a.project_root).resolve() if a.project_root else None
 env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(root)
 reports=root/'results/publication';reports.mkdir(parents=True,exist_ok=True)
 unit=run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],root,env)
 pub=reports/'publication-acceptance.json'
 run([sys.executable,'tests/publication_acceptance.py','--root','.','--out',str(pub)],root,env)
 rev=reports/'reviewer-attack-audit.json'
 cmd=[sys.executable,'tests/reviewer_attack_audit.py','--root','.','--out',str(rev)]
 if project: cmd += ['--project-root',str(project)]
 run(cmd,root,env)
 out={'status':'PASS','mode':'full-project' if project else 'artifact-only',
      'unit_test_output':unit[-4000:],
      'publication_acceptance':readpass(pub),
      'reviewer_attack_audit':readpass(rev)}
 if project:
  full=reports/'full-project-acceptance.json'
  run([sys.executable,'tests/full_project_acceptance.py','--root',str(project),'--out',str(full)],root,env)
  out['full_project_acceptance']=readpass(full)
 Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
 print('release acceptance: PASS')
if __name__=='__main__':main()
