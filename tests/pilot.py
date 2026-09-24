"""Single-process discriminating pilot; no external code or solver."""
import itertools, json, resource, time
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS, (2500*1024**2,2500*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(100,110))
start=time.process_time(); wall=time.monotonic()
transitions=0; oracle_assignments=0

def signed(x,B):
    return x if x<B//2 else x-B

def direct(q,b,s,z,mode):
    B=1<<b; M=B**len(q)
    if mode=='sub_mul':
        U=sum(((v-z)%B)*B**i for i,v in enumerate(q)); W=(s*U)%M
    else:
        U=sum(v*B**i for i,v in enumerate(q)); W=(s*U)%M
        if mode=='word_sub': W=(W-sum((s*z%B)*B**i for i in range(len(q))))%M
    out=[]
    for i in range(len(q)):
        v=(W//B**i)%B
        if mode=='mul_sub':v=(v-s*z)%B
        if mode=='sat_mul_sub':v=(min(q[i]*s,B//2-1)-s*z)%B
        out.append(signed(v,B))
    return out

def table(dom,b,s,z,mode):
    global transitions
    B=1<<b; states={(0,False):()}; layers=[states]
    for lo,hi in dom:
        nxt={}
        for (c,bad),path in states.items():
            for q in range(lo,hi+1):
                transitions+=1
                if mode=='sub_mul':t=s*((q-z)%B)+c; d=t%B; co=t//B
                elif mode=='word_sub':t=s*q-(s*z%B)+c;d=t%B;co=t//B
                elif mode=='sat_mul_sub':co=0;d=(min(q*s,B//2-1)-s*z)%B
                else:t=s*q+c;co=t//B;d=(t-s*z)%B
                key=(co,bad or signed(d,B)!=s*(q-z)); candidate=path+(q,)
                if key not in nxt or candidate<nxt[key]:nxt[key]=candidate
        states=nxt;layers.append(states)
    failures=[path for (c,bad),path in states.items() if bad]
    return min(failures) if failures else None, max(map(len,layers))

rows=[]
for b,s,z,mode in itertools.product([4,8],[0,1,2],[0,3],['mul_sub','sub_mul','word_sub','sat_mul_sub']):
    dom=[(0,3)]*2; got,width=table(dom,b,s,z,mode); expected=None
    for q in itertools.product(range(4),repeat=2):
        oracle_assignments+=1
        if direct(q,b,s,z,mode)!=[s*(v-z) for v in q] and expected is None: expected=q
    assert got==expected,(b,s,z,mode,got,expected)
    rows.append({'bits':b,'scale':s,'zero':z,'mode':mode,'witness':got,'max_states':width})
# Source-inspired, three-lane complete oracle and hard 32-bit packed pilot.
for mode in ['mul_sub','sub_mul']:
    dom=[(0,15)]*3;got,width=table(dom,8,2,8,mode);expected=None
    for q in itertools.product(range(16),repeat=3):
        oracle_assignments+=1
        if direct(q,8,2,8,mode)!=[2*(v-8) for v in q] and expected is None:expected=q
    assert got==expected
    rows.append({'bits':8,'lanes':3,'scale':2,'zero':8,'mode':mode,'witness':got,'max_states':width})
for mode in ['mul_sub','sub_mul','word_sub']:
    got,width=table([(0,15)]*8,4,15,7,mode)
    assert got is not None and direct(got,4,15,7,mode)!=[15*(v-7) for v in got]
    rows.append({'bits':4,'lanes':8,'scale':15,'zero':7,'mode':mode,'witness':got,'max_states':width})
result={'cases':len(rows),'transitions':transitions,'exhaustive_assignments':oracle_assignments,'cpu_seconds':time.process_time()-start,'wall_seconds':time.monotonic()-wall,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'rows':rows}
Path(__file__).resolve().parents[1].joinpath('results', 'intake', 'pilot.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2));print('source-schema controls',rows[-5:-3]);print('hard',rows[-3:])
