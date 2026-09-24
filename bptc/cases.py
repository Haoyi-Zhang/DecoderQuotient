"""Frozen, deterministic case inventory. These are schemas, not GPU workloads."""
from __future__ import annotations
from copy import deepcopy
from math import prod


def base(n: int=4,bits: int=8,scale: int=2,zero: int=8,domain=(0,15),mode='mul_sub') -> dict:
    return dict(id='',shape=[n],bits=bits,scale=scale,zero=zero,
                domains=[list(domain) for _ in range(n)],layout=list(range(n)),
                consume=list(range(n)),arithmetic=mode,acc_widths=[32]*n,
                acc_semantics='modular',activation_bounds=[-128,127],observations=[n],
                input_offset=0,output_offset=(n+1)//2+16,memory_bytes=(n+1)//2+20)


def inventory() -> tuple[list[dict],list[dict]]:
    cases=[];metadata=[]
    def add(c,family,detail):
        c=deepcopy(c);c['id']=f'case-{len(cases)+1:03d}'
        cases.append(c);metadata.append({'id':c['id'],'family':family,'detail':detail})
    # Six parameter boxes, all five modes, all four lane widths. No selection by outcome.
    for bits in (4,8,16,32):
        profiles=[(0,0,(0,15)),(1,8,(0,15)),(2,8,(0,15)),
                  (8,8,(0,15)),(min(16,(1<<bits)-1),8,(0,15)),
                  (min(18,(1<<bits)-1),14,(14,15))]
        for p,(s,z,d) in enumerate(profiles):
            for mode in ('mul_sub','sub_mul','word_sub','word_affine','sat_mul_sub'):
                add(base(32//bits,bits,s,z,d,mode),'word-grid',f'box {p}; {bits}-bit lanes; {mode}')
    # Size sensitivity reuses an explicitly identical local proof table.
    shapes=[[4],[4,4],[4,4,4],[4,4,4,4],[8,8,16],[8,8,8,8]]
    for shape in shapes:
        n=prod(shape);c=base(n);c['shape']=shape
        c['layout']=list(reversed(range(n)));c['consume']=c['layout'][:]
        add(c,'size-layout','fixed decoder, reversed logical order')
    c=base(4,8,18,14,(14,14));c['domains'][-1]=[14,15]
    add(c,'boundary','discarded outgoing carry of final lane')
    add(base(8,4,3,13,(13,13),'sat_mul_sub'),'boundary','saturation changes value by two lane moduli')
    # Accumulation obligations distinguish observation from transient wrap.
    c=base(32);c['acc_widths']=[16]*32
    add(c,'accumulation','final 16-bit result may overflow')
    c=base(32);c['acc_widths']=[16]*8+[32]*24
    add(c,'accumulation','signed widening after eight products')
    c=base(32);c['acc_widths']=[16]*16+[32]*16
    add(c,'accumulation','signed widening at positive endpoint 32768')
    c=base(8,8,16,8);c['domains']=[[15,15]]*4+[[1,1]]*4
    c['activation_bounds']=[1,1];c['acc_widths']=[8]*8
    add(c,'accumulation','transient modular overflow cancels before final observation')
    c['acc_semantics']='saturating'
    add(c,'accumulation','same schedule with saturation')
    c['acc_semantics']='modular';c['acc_widths']=[8]*4+[16]*4
    add(c,'accumulation','signed widening exposes transient modular overflow')
    c['acc_widths']=[16]*4+[8]*4
    add(c,'accumulation','narrowing preserves residue')
    c['acc_widths']=[8]*8;c['observations']=[4,8]
    add(c,'accumulation','explicit intermediate signed observation')
    # Contract failures are not automatically claims of a differing final value.
    c=base(32);c['consume'][0],c['consume'][1]=c['consume'][1],c['consume'][0]
    add(c,'layout','activation/weight index mismatch')
    c=base(32);c['layout'][1]=c['layout'][0];c['consume']=c['layout'][:]
    add(c,'layout','duplicate logical coordinate')
    c=base(32);c['output_offset']=0
    add(c,'layout','output aliases immutable packed input')
    c=base(32);c['memory_bytes']-=1
    add(c,'layout','output end lies outside declared memory')
    c=base(32);c['input_offset']=2**32-6;c['memory_bytes']=2**32-1
    add(c,'layout','input interval crosses 32-bit address bound')
    c=base(32);c['layout']=[i for j in range(16) for i in (j,j+16)]
    c['consume']=c['layout'][:]
    add(c,'layout','32-code interleave as an explicit bijection')
    return cases,metadata
