"""Independent replay implementation, using no producer/interpreter helpers.

This is an executable checker, not a formally verified program. Expected input
specifications are supplied separately; a certificate is not its own authority.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


class Invalid(ValueError):
    """Malformed specification or failed certificate replay."""


def _int(x: Any, low: int, high: int) -> bool:
    return type(x) is int and low <= x <= high


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def _same(actual: Any, expected: Any) -> bool:
    """Structural equality that does not identify JSON booleans with integers."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _input(c: Any) -> None:
    keys = {'id','shape','bits','scale','zero','domains','layout','consume',
            'arithmetic','acc_widths','acc_semantics','activation_bounds',
            'observations','input_offset','output_offset','memory_bytes'}
    _require(type(c) is dict and set(c) == keys, 'specification fields')
    _require(type(c['id']) is str and len(c['id']) <= 80, 'identifier')
    _require(type(c['shape']) is list and 1 <= len(c['shape']) <= 4,'rank')
    extent = 1
    for d in c['shape']:
        _require(_int(d,1,4096),'shape dimension')
        extent *= d
    _require(_int(extent,1,4096),'tensor size')
    b = c['bits']
    _require(_int(b,4,32) and b in (4,8,16,32),'lane width')
    _require(extent % (32//b) == 0,'partial word not supported')
    _require(_int(c['scale'],0,min(31,(1<<b)-1)),'integer scale')
    _require(_int(c['zero'],0,15),'integer zero point')
    _require(c['arithmetic'] in ('mul_sub','sub_mul','word_sub','word_affine','sat_mul_sub'),'arithmetic mode')
    _require(type(c['domains']) is list and len(c['domains'])==extent,'domains')
    for d in c['domains']:
        _require(type(d) is list and len(d)==2 and _int(d[0],0,15)
                 and _int(d[1],d[0],15),'code interval')
    for field in ('layout','consume'):
        _require(type(c[field]) is list and len(c[field])==extent and
                 all(_int(i,0,extent-1) for i in c[field]),'index vector')
    _require(type(c['acc_widths']) is list and len(c['acc_widths'])==extent and
             all(_int(w,4,32) and w in (4,8,16,32) for w in c['acc_widths']),'accumulator widths')
    _require(c['acc_semantics'] in ('modular','saturating'),'accumulator semantics')
    a = c['activation_bounds']
    _require(type(a) is list and len(a)==2 and _int(a[0],-128,127)
             and _int(a[1],a[0],127),'activation bounds')
    _require(type(c['observations']) is list and len(c['observations'])<=extent
             and all(_int(i,1,extent) for i in c['observations'])
             and len(set(c['observations']))==len(c['observations']),'observations')
    for k in ('input_offset','output_offset','memory_bytes'):
        _require(_int(c[k],0,(1<<32)-1),'memory extent')


def _layer(records: Any, depth: int, domains: list[list[int]]) -> dict:
    _require(type(records) is list and 1 <= len(records) <= 128,'state count')
    result = {}
    for r in records:
        _require(type(r) is dict and set(r)=={'carry','bad','prefix'},'state fields')
        _require(_int(r['carry'],-32,32) and type(r['bad']) is bool,'state label')
        p=r['prefix']
        _require(type(p) is list and len(p)==depth,'prefix length')
        _require(all(_int(x,*domains[i]) for i,x in enumerate(p)),'prefix domain')
        key=(r['carry'],r['bad'])
        _require(key not in result,'duplicate state')
        result[key]=tuple(p)
    _require([(r['carry'],r['bad']) for r in records] == sorted(result),'state order')
    return result


def _table(t: Any, c: dict, counters: dict | None = None) -> tuple[bool,int,int]:
    _require(type(t) is dict and set(t)=={'domains','layers','witness','transitions'},'table fields')
    ds=t['domains']; count=32//c['bits']; base=2**c['bits']
    _require(type(ds) is list and len(ds)==count,'table domain length')
    for d in ds:
        _require(type(d) is list and len(d)==2 and _int(d[0],0,15)
                 and _int(d[1],d[0],15),'table interval')
    _require(type(t['layers']) is list and len(t['layers'])==count+1,'layer count')
    current=_layer(t['layers'][0],0,ds)
    _require(current=={(0,False):()},'initial state')
    transitions=0; maximum=len(current)
    for position in range(count):
        next_states={}
        for state,path in current.items():
            for value in range(ds[position][0],ds[position][1]+1):
                transitions+=1
                if counters is not None: counters["transitions"] = counters.get("transitions",0)+1
                carry,already_bad=state
                mode=c['arithmetic']; scale=c['scale']; zero=c['zero']
                if mode=='sat_mul_sub':
                    product=scale*value
                    clipped=product if product<base//2 else base//2-1
                    out=(clipped-scale*zero)&(base-1)
                    following_carry=0
                else:
                    operand=value
                    subtract=0
                    if mode=='sub_mul': operand=(value-zero)&(base-1)
                    if mode=='word_sub': subtract=(scale*zero)&(base-1)
                    if mode=='word_affine': subtract=scale*zero
                    full=scale*operand-subtract+carry
                    following_carry=full//base
                    out=full-following_carry*base
                    if mode=='mul_sub': out=(out-scale*zero)&(base-1)
                interpreted=out-base if out >= base//2 else out
                bad=already_bad or interpreted != scale*(value-zero)
                successor=(following_carry,bad)
                prefix=path+(value,)
                old=next_states.get(successor)
                if old is None or prefix<old:
                    next_states[successor]=prefix
        claimed=_layer(t['layers'][position+1],position+1,ds)
        _require(claimed==next_states,'transition closure or minimal-prefix label')
        current=claimed;maximum=max(maximum,len(current))
    witnesses=[path for (_,bad),path in current.items() if bad]
    witness=list(min(witnesses)) if witnesses else None
    _require(_same(t['witness'],witness),'counterexample claim')
    _require(type(t['transitions']) is int and t['transitions']==transitions,'transition count')
    return not witnesses,transitions,maximum


def verify(c: dict, cert: dict, counters: dict | None = None) -> dict:
    _input(c)
    _require(type(cert) is dict and set(cert)=={'binding','tables','block_table',
             'layout_satisfied','decode_satisfied','accumulation','stage'},'certificate fields')
    # Structural equality is intentionally used instead of a checksum manifest.
    _require(_same(cert['binding'],c),'certificate not bound to supplied specification')
    n=len(c['domains']); lanes=32//c['bits']; B=2**32
    indexes=c['layout']
    layout_ok=(len(set(indexes))==n and indexes==c['consume'])
    input_end=c['input_offset']+(n+1)//2;output_end=c['output_offset']+4
    layout_ok=layout_ok and input_end<=min(B,c['memory_bytes']) and output_end<=min(B,c['memory_bytes'])
    layout_ok=layout_ok and (input_end<=c['output_offset'] or output_end<=c['input_offset'])
    _require(type(cert['layout_satisfied']) is bool and cert['layout_satisfied']==layout_ok,'layout conclusion')
    tables=cert['tables'];refs=cert['block_table']
    _require(type(tables) is list and 1<=len(tables)<=n//lanes,'table inventory')
    _require(type(refs) is list and len(refs)==n//lanes and
             all(_int(r,0,len(tables)-1) for r in refs),'block references')
    _require(set(refs)==set(range(len(tables))),'unreferenced table')
    for j,r in enumerate(refs):
        expected=[c['domains'][indexes[k]] for k in range(j*lanes,(j+1)*lanes)]
        _require(type(tables[r]) is dict and tables[r].get('domains')==expected,'table-to-block binding')
    unique=set()
    good=True;transitions=0;maximum=0
    for t in tables:
        key=tuple(tuple(d) for d in t['domains'])
        _require(key not in unique,'duplicate table signature')
        unique.add(key)
        accepted,cost,width=_table(t,c,counters)
        good=good and accepted;transitions+=cost;maximum=max(maximum,width)
    _require(type(cert['decode_satisfied']) is bool and cert['decode_satisfied']==good,'decode conclusion')
    checkpoint=set(c['observations']);checkpoint.add(n)
    for j in range(n):
        if c['acc_semantics']=='saturating': checkpoint.add(j+1)
        elif j and c['acc_widths'][j]>c['acc_widths'][j-1]: checkpoint.add(j)
    lower=upper=0;checks=[]
    for j,k in enumerate(indexes):
        endpoints=[]
        for a in c['activation_bounds']:
            for q in c['domains'][k]: endpoints.append(a*c['scale']*(q-c['zero']))
        lower+=min(endpoints);upper+=max(endpoints)
        if j+1 in checkpoint:
            width=c['acc_widths'][j]
            good_range=(lower>=-2**(width-1) and upper<=2**(width-1)-1)
            checks.append(dict(prefix=j+1,bits=width,lower=lower,upper=upper,fits=good_range))
    acc={'checks':checks,'satisfied':all(x['fits'] for x in checks)}
    _require(_same(cert['accumulation'],acc),'accumulation obligation')
    stage=('layout' if not layout_ok else 'decode' if not good else
           'accumulation' if not acc['satisfied'] else 'accepted')
    _require(cert['stage']==stage,'stage classification')
    return {'certificate_valid':True,'accepted':stage=='accepted','stage':stage,
            'transitions':transitions,'maximum_states':maximum,'unique_tables':len(tables)}


def load_json(path: str | Path, maximum_bytes: int = 8*1024*1024) -> Any:
    p=Path(path)
    _require(p.is_file() and p.stat().st_size<=maximum_bytes,'file missing or too large')
    with p.open('r',encoding='utf-8') as f:
        return json.load(f)
