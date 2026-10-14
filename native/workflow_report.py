#!/usr/bin/env python3
"""Source-bound complete-workflow table/CSV/vector plot; never measures time.

SPDX-License-Identifier: MIT. Retains every case median, including slow cases.
"""
import argparse
import csv
import importlib.util
import io
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native.workflow_cost import check
from bptc.certificate_format import exact
from native.bridge import panel_text


def group(row):
    name=row['case']
    if row['original']: return 'Original schedules'
    if name.endswith('-unique'): return 'Unique products'
    if name.endswith('-duplicate'): return 'Duplicate products'
    return 'Boundary controls'


def inputs(root):
    check(root)
    panel=json.loads((root/'panel.json').read_text())
    for i,spec in enumerate(panel['accumulators']):
        exact((root/'inputs'/f'{i:02d}.txt').read_text(),
              panel_text(dict(accumulators=[spec],decoders=[])), 'measured declaration input')
    rows=json.loads((root/'summary.json').read_text())['rows']
    original=[r for r in rows if r['original']]
    slower=sum(r['median_ratio']<1 for r in original)
    minimum=min(r['median_ratio'] for r in original)
    maximum=max(r['median_ratio'] for r in original)
    protocol=json.loads((root/'protocol.json').read_text())
    vals={'WorkflowPairs':protocol['samples'],'WorkflowOriginalSlower':slower,
          'WorkflowAllSlower':sum(r['median_ratio']<1 for r in rows),
          'WorkflowMin':f'{minimum:.3f}','WorkflowMax':f'{maximum:.3f}',
          'WorkflowMedian':f"{statistics.median(r['median_ratio'] for r in original):.3f}",
          'WorkflowUsMin':f"{min(r['quotient_median_ns'] for r in original)/1e6:.2f}",
          'WorkflowUsMax':f"{max(r['quotient_median_ns'] for r in original)/1e6:.2f}"}
    macros='% Derived from the source-bound complete workflow, not native component sums.\n'
    macros+=''.join('\\newcommand{\\'+k+'}{'+str(v)+'}\n' for k,v in vals.items())
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,lineterminator='\n',fieldnames=['case','group','paired_median_ratio',
        'quotient_median_ns','pairs_median_ns','quotient_bytes','pairs_bytes'])
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(case=row['case'],group=group(row),paired_median_ratio=row['median_ratio'],
            **{k:row[k] for k in ('quotient_median_ns','pairs_median_ns','quotient_bytes','pairs_bytes')}))
    return rows,macros,stream.getvalue()


def draw(rows,paper):
    source=paper/'figures/draw_evaluation.py'
    spec=importlib.util.spec_from_file_location('retained_font_renderer',source)
    fonts=importlib.util.module_from_spec(spec);spec.loader.exec_module(fonts)
    fonts.register_fonts('libertine')
    from reportlab.pdfgen import canvas
    target=paper/'figures/workflow-cost.pdf'
    c=canvas.Canvas(str(target),pagesize=(428.4,150),invariant=True,initialFontName='Body')
    c.setFont('Body',9)
    left,width,bottom=120,295,34
    def x(r): return left+width*(math.log2(r)+1)/4
    c.setLineWidth(.4)
    for tick in (.5,1,2,4,8):
        c.setStrokeGray(.8)
        c.line(x(tick),bottom,x(tick),138)
        c.setFillGray(0);c.drawCentredString(x(tick),bottom-13,str(tick))
    c.setStrokeGray(0);c.setDash(3,2);c.line(x(1),bottom,x(1),138);c.setDash()
    groups=['Original schedules','Duplicate products','Unique products','Boundary controls']
    for i,name in enumerate(groups):
        y=124-i*26
        subset=[r for r in rows if group(r)==name]
        c.setFillGray(0);c.drawRightString(left-9,y-3,f'{name} ({len(subset)})')
        for j,row in enumerate(subset):
            ratio=row['median_ratio']
            if not .5 <= ratio <= 8: raise ValueError('plot axis clips a case median')
            # Vertical offsets separate symbols; they are not another statistic.
            shift=((j%7)-3)*1.4
            c.setStrokeGray(0);c.setFillGray(.65 if row['original'] else .2)
            c.circle(x(ratio),y+shift,1.8,stroke=1,fill=1)
    c.setFillGray(0)
    c.drawCentredString(left+width/2,5,'Pair workflow / quotient workflow (log2 scale; tie = 1)')
    c.showPage();c.save()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results-dir',type=Path,required=True)
    p.add_argument('--paper-dir',type=Path,required=True)
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    rows,macros,table=inputs(a.results_dir)
    outputs={a.paper_dir/'generated/workflow_macros.tex':macros,
             a.paper_dir/'figures/workflow-cost.csv':table}
    for path,body in outputs.items():
        if a.check: exact(path.read_text(),body,'workflow derived input')
        else: path.write_text(body,encoding='utf-8',newline='')
    if not a.check: draw(rows,a.paper_dir)
    print('Complete workflow: 79 case rows; 553 raw pairs; no timing or positive-result filtering.')


if __name__=='__main__':main()
