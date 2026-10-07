// SPDX-License-Identifier: MIT. Original P053 material; see ../LICENSE.
// Native realization of the declared finite language, not a CUDA frontend.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#elif defined(__linux__)
#include <sched.h>
#else
#error Native affinity implementation currently requires Windows or Linux
#endif
using I=std::int64_t;
using Word=std::vector<int>;
static I charged=0;
static constexpr I cap=2000000;
static volatile std::uint64_t sink=0;
static void require(bool ok,const char* why) {if(!ok)throw std::runtime_error(why);}
static void charge(I n=1) {require(n>=0&&n<=cap-charged,"native conformance event cap");charged+=n;}
static I narrow(__int128 z) {require(z>=std::numeric_limits<I>::min()&&z<=std::numeric_limits<I>::max(),"outside int64 native subset");return static_cast<I>(z);}
struct Affinity {std::string original_mask,actual_mask;int cpu;};
static std::string mask_hex(const std::vector<int>& cpus) {
    int highest=cpus.empty()?0:*std::max_element(cpus.begin(),cpus.end());
    std::string mask(static_cast<std::size_t>(highest/4+1),'0');
    for(int cpu:cpus){std::size_t pos=mask.size()-1-static_cast<std::size_t>(cpu/4);char c=mask[pos];int v=c<='9'?c-'0':c-'a'+10;v|=1<<(cpu%4);mask[pos]="0123456789abcdef"[v];}
    return "0x"+mask;
}
// This is invoked for correctness runs too, without reading a timer. The
// measurement entry invokes it before any warmup or timed native operation.
static Affinity pin_available_cpu() {
    std::vector<int> original,actual;
#ifdef _WIN32
    DWORD_PTR allowed=0,system=0;
    require(GetProcessAffinityMask(GetCurrentProcess(),&allowed,&system)!=0,"cannot query process affinity");
    for(int i=0;i<static_cast<int>(sizeof(DWORD_PTR)*8);i++)if(allowed&(DWORD_PTR(1)<<i))original.push_back(i);
    require(!original.empty(),"no available logical CPU");
    const int cpu=original.front();const DWORD_PTR chosen=DWORD_PTR(1)<<cpu;
    require(SetProcessAffinityMask(GetCurrentProcess(),chosen)!=0,"cannot pin native process");
    DWORD_PTR observed=0;
    require(GetProcessAffinityMask(GetCurrentProcess(),&observed,&system)!=0&&observed==chosen,"actual process affinity differs from requested mask");
    actual.push_back(cpu);
#else
    cpu_set_t allowed,chosen,observed;CPU_ZERO(&allowed);CPU_ZERO(&chosen);CPU_ZERO(&observed);
    require(sched_getaffinity(0,sizeof(allowed),&allowed)==0,"cannot query thread affinity");
    for(int i=0;i<CPU_SETSIZE;i++)if(CPU_ISSET(i,&allowed))original.push_back(i);
    require(!original.empty(),"no available logical CPU");const int cpu=original.front();CPU_SET(cpu,&chosen);
    require(sched_setaffinity(0,sizeof(chosen),&chosen)==0,"cannot pin native thread");
    require(sched_getaffinity(0,sizeof(observed),&observed)==0&&CPU_COUNT(&observed)==1&&CPU_ISSET(cpu,&observed),"actual thread affinity differs from requested mask");
    actual.push_back(cpu);
#endif
    return {mask_hex(original),mask_hex(actual),original.front()};
}
static bool flag(int n) {require(n==0||n==1,"flag must be 0 or 1");return n!=0;}
static bool mode(const std::string& m) {require(m=="wrap"||m=="saturate","conversion mode");return m=="saturate";}
static void identifier(const std::string& s) {require(!s.empty()&&s.size()<128,"identifier length");for(char c:s)require((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'||c=='_',"identifier character");}
struct Stage {std::vector<std::array<I,2>> pairs;int tw,aw;bool ts,as,observe;};
struct Spec {std::string name,provenance;I initial;bool final;std::vector<Stage> stages;};
struct Decoder {std::string name,provenance;int scale;std::vector<int> maxima,biases;};
struct Panel {std::vector<Spec> acc;std::vector<Decoder> dec;};
static Panel read_panel(const std::string& path) {
    std::ifstream f(path);require(bool(f),"cannot open panel");std::string header;int na=0,nd=0;f>>header>>na>>nd;
    require(header=="p053-native-panel-v1"&&na>=1&&na<=128&&nd>=0&&nd<=64,"panel header/counts");Panel p;std::set<std::string> names;
    for(int k=0;k<na;k++) {
        char tag;int n,fin;Spec s;f>>tag>>s.name>>s.provenance>>s.initial>>fin>>n;
        require(tag=='A'&&n>=1&&n<=64,"accumulator declaration");identifier(s.name);identifier(s.provenance);require(names.insert(s.name).second,"duplicate case");s.final=flag(fin);
        __int128 lo=s.initial,hi=lo;
        for(int i=0;i<n;i++) {
            Stage st;int obs,np;std::string tm,am;f>>tag>>st.tw>>tm>>st.aw>>am>>obs>>np;
            require(tag=='S'&&st.tw>=2&&st.tw<=32&&st.aw>=2&&st.aw<=32&&np>=1&&np<=4096,"stage declaration");st.ts=mode(tm);st.as=mode(am);st.observe=flag(obs);
            std::set<std::array<I,2>> seen;I mn=0,mx=0;
            for(int j=0;j<np;j++){std::array<I,2> a;f>>tag>>a[0]>>a[1];require(tag=='P'&&bool(f)&&seen.insert(a).second,"operand pair declaration");I prod=narrow(static_cast<__int128>(a[0])*a[1]);if(j==0){mn=mx=prod;}mn=std::min(mn,prod);mx=std::max(mx,prod);st.pairs.push_back(a);}
            lo+=mn;hi+=mx;narrow(lo);narrow(hi);s.stages.push_back(st);
        }require(bool(f),"truncated accumulator");p.acc.push_back(s);
    }
    for(int k=0;k<nd;k++) {
        char tag;int n;Decoder d;f>>tag>>d.name>>d.provenance>>d.scale>>n;
        require(tag=='D'&&n>=1&&n<=4&&d.scale>=0&&d.scale<=255,"decoder declaration");identifier(d.name);identifier(d.provenance);require(names.insert(d.name).second,"duplicate case");
        for(int i=0;i<n;i++){int mx,b;f>>mx>>b;require(mx>=0&&mx<=15&&b>=0&&b<=255,"decoder bounds");d.maxima.push_back(mx);d.biases.push_back(b);}require(bool(f),"truncated decoder");p.dec.push_back(d);
    }
    std::string trailing;require(!(f>>trailing),"trailing panel tokens");return p;
}
// No signed overflow or implementation-defined signed narrowing is used.
extern "C" __attribute__((noinline)) I p053_convert(I z,int w,bool sat) {
    const I half=I(1)<<(w-1),ring=I(1)<<w;
    if(sat)return z< -half ? -half : z>=half ? half-1 : z;
    I r=z%ring;if(r<0)r+=ring;return r>=half?r-ring:r;
}
struct State {
    I t,e;bool bad;int first;
    bool operator<(const State& o)const{return std::tie(t,e,bad,first)<std::tie(o.t,o.e,o.bad,o.first);}
};
struct Branch {I product;int rep;Word members;};
using Branches=std::vector<std::vector<Branch>>;
using Frontier=std::map<State,Word>;
struct Edge {State from,to;I product;int rep;};
struct Layer {Frontier states;std::vector<Edge> edges;};
struct Graph {std::vector<Layer> layers;I edges=0,u=0,words=1,sequences=1;};
static Branches prepare(const Spec& s,bool quotient,bool account=false) {
    Branches all;
    for(const auto& st:s.stages) {
        std::vector<Branch> b;std::map<I,std::size_t> by;
        for(std::size_t j=0;j<st.pairs.size();j++){
            if(account)charge();I product=narrow(static_cast<__int128>(st.pairs[j][0])*st.pairs[j][1]);auto it=by.find(product);
            if(quotient&&it!=by.end())b[it->second].members.push_back(static_cast<int>(j));
            else {if(quotient)by[product]=b.size();b.push_back({product,static_cast<int>(j),{static_cast<int>(j)}});}
        }all.push_back(std::move(b));
    }return all;
}
extern "C" __attribute__((noinline)) State p053_advance(State old,I product,const Spec* spec,std::size_t i) {
    const Stage& st=spec->stages[i];const Stage& prev=spec->stages[i?i-1:0];
    const I actual=p053_convert(old.t,prev.aw,prev.as)+old.e;
    const I value=p053_convert(actual+p053_convert(product,st.tw,st.ts),st.aw,st.as);
    const I target=narrow(static_cast<__int128>(old.t)+product),reference=p053_convert(target,st.aw,st.as),error=value-reference;
    const bool fail=(st.observe||(spec->final&&i+1==spec->stages.size()))&&error!=0;
    return {target,error,old.bad||fail,fail&&!old.bad?static_cast<int>(i):old.first};
}
static Graph walk(const Spec& s,const Branches& branches,bool account=false) {
    Graph g;g.layers.push_back({{{{s.initial,0,false,-1},{}}},{}});
    for(std::size_t i=0;i<s.stages.size();i++) {
        Layer next;const auto& current=g.layers.back().states;
        g.u+=static_cast<I>(current.size()*s.stages[i].pairs.size());
        g.words=narrow(static_cast<__int128>(g.words)*s.stages[i].pairs.size());g.sequences=narrow(static_cast<__int128>(g.sequences)*branches[i].size());
        for(const auto& kv:current)for(const auto& b:branches[i]) {
            if(account)charge();g.edges++;State to=p053_advance(kv.first,b.product,&s,i);Word candidate=kv.second;candidate.push_back(b.rep);
            auto it=next.states.find(to);if(it==next.states.end()||candidate<it->second)next.states[to]=candidate;
            next.edges.push_back({kv.first,to,b.product,b.rep});
            require(next.states.size()<=50000&&g.edges<=100000,"per-graph size cap");
        }
        g.layers.push_back(std::move(next));
    }return g;
}
// Small JSON writer: inputs are strict identifiers, integral values and flags.
static void json_bool(std::ostream& o,bool b){o<<(b?"true":"false");}
static void word(std::ostream& o,const Word& w){o<<'[';for(std::size_t i=0;i<w.size();i++){if(i)o<<',';o<<w[i];}o<<']';}
static void pair(std::ostream& o,const std::array<I,2>& p){o<<'['<<p[0]<<','<<p[1]<<']';}
static void state(std::ostream& o,const State& s){o<<'['<<s.t<<','<<s.e<<',';json_bool(o,s.bad);o<<','<<s.first<<']';}
static void pairs(std::ostream& o,const Spec& s,const Word& w){o<<'[';for(std::size_t i=0;i<w.size();i++){if(i)o<<',';pair(o,s.stages[i].pairs[static_cast<std::size_t>(w[i])]);}o<<']';}
static void spec_json(std::ostream& o,const Spec& s) {
    o<<"{\"name\":\""<<s.name<<"\",\"provenance\":\""<<s.provenance<<"\",\"initial\":"<<s.initial<<",\"final_observe\":";json_bool(o,s.final);o<<",\"stages\":[";
    for(std::size_t i=0;i<s.stages.size();i++){if(i)o<<',';const Stage& st=s.stages[i];o<<"{\"pairs\":[";for(std::size_t j=0;j<st.pairs.size();j++){if(j)o<<',';pair(o,st.pairs[j]);}o<<"],\"term_bits\":"<<st.tw<<",\"term_mode\":\""<<(st.ts?"saturate":"wrap")<<"\",\"acc_bits\":"<<st.aw<<",\"acc_mode\":\""<<(st.as?"saturate":"wrap")<<"\",\"observe\":";json_bool(o,st.observe);o<<'}';}o<<"]}";
}
static void layers_json(std::ostream& o,const Spec& s,const Graph& g) {
    o<<'[';for(std::size_t i=0;i<g.layers.size();i++) {
        if(i)o<<',';o<<"{\"index\":"<<i<<",\"states\":[";bool first=true;
        for(const auto& kv:g.layers[i].states){if(!first)o<<',';first=false;o<<"{\"state\":";state(o,kv.first);o<<",\"least_witness_indices\":";word(o,kv.second);o<<",\"least_witness_pairs\":";pairs(o,s,kv.second);o<<'}';}o<<']';
        if(i){o<<",\"edges\":[";first=true;for(const auto& e:g.layers[i].edges){if(!first)o<<',';first=false;o<<"{\"from\":";state(o,e.from);o<<",\"product\":"<<e.product<<",\"representative_index\":"<<e.rep<<",\"to\":";state(o,e.to);o<<'}';}o<<']';}o<<'}';
    }o<<']';
}
static void decision_json(std::ostream& o,const Spec& s,const Graph& g) {
    const auto& final=g.layers.back().states;const Word* least=nullptr;State ls{};int bad=0;
    for(const auto& kv:final)if(kv.first.bad){bad++;if(!least||kv.second<*least){least=&kv.second;ls=kv.first;}}
    o<<"{\"equivalent\":";json_bool(o,bad==0);o<<",\"reachable_final_states\":"<<final.size()<<",\"bad_final_states\":"<<bad<<",\"least_counterexample\":";
    if(!least)o<<"null";else {o<<"{\"indices\":";word(o,*least);o<<",\"pairs\":";pairs(o,s,*least);o<<",\"first_bad_stage\":"<<ls.first<<",\"final_state\":";state(o,ls);o<<'}';}o<<'}';
}
static void certificate_json(std::ostream& o,const Spec& s,const Branches& b,const Graph& g) {
    o<<"{\"format\":\"bptc-exact-accumulator-certificate-v1\",\"spec\":";spec_json(o,s);o<<",\"product_classes\":[";
    for(std::size_t i=0;i<b.size();i++){if(i)o<<',';o<<'[';for(std::size_t j=0;j<b[i].size();j++){if(j)o<<',';const auto& c=b[i][j];o<<"{\"product\":"<<c.product<<",\"representative_index\":"<<c.rep<<",\"representative_pair\":";pair(o,s.stages[i].pairs[static_cast<std::size_t>(c.rep)]);o<<",\"member_indices\":";word(o,c.members);o<<",\"member_pairs\":[";for(std::size_t k=0;k<c.members.size();k++){if(k)o<<',';pair(o,s.stages[i].pairs[static_cast<std::size_t>(c.members[k])]);}o<<"]}";}o<<']';}
    o<<"],\"layers\":";layers_json(o,s,g);o<<",\"decision\":";decision_json(o,s,g);o<<",\"metrics\":{\"concrete_assignments\":"<<g.words<<",\"quotient_product_sequences\":"<<g.sequences<<",\"producer_transitions\":"<<g.edges<<",\"unquotiented_frontier_edges\":"<<g.u<<",\"quotient_frontier_edges\":"<<g.edges<<"}}";
}
static std::vector<Word> concrete_words(const Spec& s,I count) {
    std::vector<Word> words;const std::size_t n=s.stages.size();
    if(count<=10000)for(I k=0;k<count;k++){I r=k;Word ix(n);for(std::size_t i=n;i-->0;){ix[i]=static_cast<int>(r%static_cast<I>(s.stages[i].pairs.size()));r/=static_cast<I>(s.stages[i].pairs.size());}words.push_back(ix);}
    else {words.push_back(Word(n,0));Word last;for(const auto& st:s.stages)last.push_back(static_cast<int>(st.pairs.size()-1));words.push_back(last);}
    return words;
}
static void concrete_json(std::ostream& o,const Spec& s,const Graph& g) {
    auto words=concrete_words(s,g.words);o<<"{\"whole_box_enumerated\":";json_bool(o,g.words<=10000);o<<",\"traces\":[";
    for(std::size_t k=0;k<words.size();k++){
        charge();if(k)o<<',';const Word& ix=words[k];I t=s.initial,l=p053_convert(t,s.stages[0].aw,s.stages[0].as);int first=-1;o<<"{\"indices\":";word(o,ix);o<<",\"steps\":[";
        for(std::size_t i=0;i<s.stages.size();i++) {
            const Stage& st=s.stages[i];const auto& p=st.pairs[static_cast<std::size_t>(ix[i])];const I prod=narrow(static_cast<__int128>(p[0])*p[1]),term=p053_convert(prod,st.tw,st.ts);
            t=narrow(static_cast<__int128>(t)+prod);l=p053_convert(l+term,st.aw,st.as);const I ref=p053_convert(t,st.aw,st.as);const bool obs=st.observe||(s.final&&i+1==s.stages.size());if(obs&&l!=ref&&first<0)first=static_cast<int>(i);
            if(i)o<<',';o<<"{\"stage\":"<<i<<",\"pair\":";pair(o,p);o<<",\"product\":"<<prod<<",\"term\":"<<term<<",\"target\":"<<t<<",\"lowered\":"<<l<<",\"reference\":"<<ref<<",\"observed\":";json_bool(o,obs);o<<",\"first_bad\":"<<first<<'}';
        }o<<"]}";
    }o<<"]}";
}
extern "C" __attribute__((noinline)) std::uint32_t p053_packed(std::uint32_t word,std::uint32_t scale,const int* biases,int lanes) {
    const std::uint32_t multiplied=word*scale;std::uint32_t answer=0;
    for(int i=0;i<lanes;i++)answer|=(((multiplied>>(8*i))+static_cast<std::uint32_t>(biases[i]))&255U)<<(8*i);return answer;
}
extern "C" __attribute__((noinline)) std::uint32_t p053_lane_reference(std::uint32_t word,std::uint32_t scale,const int* biases,int lanes) {
    std::uint32_t answer=0;for(int i=0;i<lanes;i++)answer|=((((word>>(8*i))&255U)*scale+static_cast<std::uint32_t>(biases[i]))&255U)<<(8*i);return answer;
}
static bool decoder_safe(const Decoder& d,int& carry){carry=0;bool safe=true;for(int mx:d.maxima){if(carry)safe=false;carry=(d.scale*mx+carry)/256;}return safe;}
static void decoder_json(std::ostream& o,const Decoder& d) {
    int count=1;for(int x:d.maxima)count*=x+1;int carry;const bool safe=decoder_safe(d,carry);o<<"{\"name\":\""<<d.name<<"\",\"equivalent\":";json_bool(o,safe);o<<",\"max_carry_after_last_lane\":"<<carry<<",\"whole_box_enumerated\":";json_bool(o,count<=4096);o<<",\"traces\":[";
    std::vector<Word> words;if(count<=4096)for(int k=0;k<count;k++){int r=k;Word digits(d.maxima.size());for(std::size_t i=digits.size();i-->0;){digits[i]=r%(d.maxima[i]+1);r/=d.maxima[i]+1;}words.push_back(digits);}else {words.push_back(Word(d.maxima.size(),0));words.push_back(d.maxima);}
    for(std::size_t k=0;k<words.size();k++){charge();if(k)o<<',';std::uint32_t w=0;for(std::size_t i=0;i<words[k].size();i++)w|=static_cast<std::uint32_t>(words[k][i])<<(8*i);o<<"{\"digits\":";word(o,words[k]);o<<",\"input_word\":"<<w<<",\"packed_output\":"<<p053_packed(w,static_cast<std::uint32_t>(d.scale),d.biases.data(),static_cast<int>(d.biases.size()))<<",\"reference_output\":"<<p053_lane_reference(w,static_cast<std::uint32_t>(d.scale),d.biases.data(),static_cast<int>(d.biases.size()))<<'}';}o<<"]}";
}
static void affinity_json(std::ostream& o,const Affinity& a) {
    o<<"{\"selected_logical_cpu\":"<<a.cpu<<",\"original_mask_hex\":\""<<a.original_mask<<"\",\"actual_mask_hex\":\""<<a.actual_mask<<"\",\"verified_single_cpu\":true}";
}
static void conform(std::ostream& o,const Panel& p) {
    const Affinity affinity=pin_available_cpu();
    o<<"{\"format\":\"p053-native-conformance-v1\",\"performance_measured\":false,\"affinity\":";affinity_json(o,affinity);o<<",\"accumulators\":[";
    for(std::size_t k=0;k<p.acc.size();k++){if(k)o<<',';const auto& s=p.acc[k];auto q=prepare(s,true,true),u=prepare(s,false,true);auto qg=walk(s,q,true),ug=walk(s,u,true);o<<"{\"name\":\""<<s.name<<"\",\"quotient_certificate\":";certificate_json(o,s,q,qg);o<<",\"baseline_layers\":";layers_json(o,s,ug);o<<",\"baseline_decision\":";decision_json(o,s,ug);o<<",\"baseline_edges\":"<<ug.edges<<",\"concrete\":";concrete_json(o,s,qg);o<<'}';}
    o<<"],\"decoders\":[";for(std::size_t k=0;k<p.dec.size();k++){if(k)o<<',';decoder_json(o,p.dec[k]);}o<<"],\"charges\":"<<charged<<",\"cap\":"<<cap<<"}\n";
}
static I tick(){return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
// Compiler memory barrier plus observable checksum prevents loop-invariant
// motion/dead-code removal of repeated kernels. It is identical for both arms.
template<class F> static I timed(int batch,F fn){I start=tick();for(int k=0;k<batch;k++){asm volatile("" ::: "memory");sink=fn();}return tick()-start;}
static void environment_json(std::ostream& o){o<<"{\"pointer_bits\":"<<sizeof(void*)*8<<",\"compiler\":\""<<__clang_version__<<"\",\"clock\":\"steady_clock nanoseconds\",\"clock_is_steady\":";json_bool(o,std::chrono::steady_clock::is_steady);o<<'}';}
static void measure(std::ostream& o,const Panel& p,const std::string& slot) {
    identifier(slot);const Affinity affinity=pin_available_cpu();
    const int batch=128,reps=21;bool first=true;o<<"{\"format\":\"p053-native-measurement-v1\",\"slot\":\""<<slot<<"\",\"affinity\":";affinity_json(o,affinity);o<<",\"environment\":";environment_json(o);o<<",\"samples\":[";
    for(const auto& s:p.acc){auto q=prepare(s,true),u=prepare(s,false);for(int k=0;k<16;k++){sink=static_cast<std::uint64_t>(walk(s,q).edges);sink=static_cast<std::uint64_t>(walk(s,u).edges);}const auto frozen=walk(s,q);
        for(int rep=0;rep<reps;rep++){
            I qt=0,ut=0;bool qfirst=rep%2==1;for(int turn=0;turn<2;turn++){bool use=(turn==0)==qfirst;I t=timed(batch,[&](){auto g=walk(s,use?q:u);return static_cast<std::uint64_t>(g.edges+g.layers.back().states.size());});if(use)qt=t;else ut=t;}
            I qp=0,up=0;for(int turn=0;turn<2;turn++){bool use=(turn==0)==qfirst;I t=timed(batch,[&](){auto b=prepare(s,use);std::size_t total=0;for(const auto& v:b)total+=v.size();return static_cast<std::uint64_t>(total);});if(use)qp=t;else up=t;}
            I ser=timed(batch,[&](){std::ostringstream x;certificate_json(x,s,q,frozen);return static_cast<std::uint64_t>(x.str().size());});
            if(!first)o<<',';first=false;o<<"{\"kind\":\"accumulator\",\"case\":\""<<s.name<<"\",\"pair\":"<<rep<<",\"order\":\""<<(qfirst?"QU":"UQ")<<"\",\"batch\":"<<batch<<",\"quotient_ns\":"<<qt<<",\"baseline_ns\":"<<ut<<",\"quotient_prepare_ns\":"<<qp<<",\"baseline_prepare_ns\":"<<up<<",\"quotient_serialize_ns\":"<<ser<<'}';
        }
    }
    for(const auto& d:p.dec){int c;if(!decoder_safe(d,c))continue;std::vector<std::uint32_t> words(1024,0);for(std::size_t k=0;k<words.size();k++)for(std::size_t i=0;i<d.maxima.size();i++)words[k]|=static_cast<std::uint32_t>((k*(2*i+1)+i)%static_cast<std::size_t>(d.maxima[i]+1))<<(8*i);
        auto kernel=[&](bool packed){std::uint64_t sum=0;for(auto w:words)sum+=packed?p053_packed(w,static_cast<std::uint32_t>(d.scale),d.biases.data(),static_cast<int>(d.biases.size())):p053_lane_reference(w,static_cast<std::uint32_t>(d.scale),d.biases.data(),static_cast<int>(d.biases.size()));return sum;};
        for(int k=0;k<16;k++){sink=kernel(true);sink=kernel(false);}for(int rep=0;rep<reps;rep++){I pn=0,rn=0;bool pf=rep%2==1;for(int turn=0;turn<2;turn++){bool use=(turn==0)==pf;I t=timed(batch,[&](){return kernel(use);});if(use)pn=t;else rn=t;}if(!first)o<<',';first=false;o<<"{\"kind\":\"decoder\",\"case\":\""<<d.name<<"\",\"pair\":"<<rep<<",\"order\":\""<<(pf?"PR":"RP")<<"\",\"batch\":"<<batch<<",\"words_per_batch\":1024,\"packed_ns\":"<<pn<<",\"reference_ns\":"<<rn<<'}';}
    }o<<"],\"sink\":"<<sink<<"}\n";
}
int main(int argc,char** argv) {
    try {
        require(argc==4||argc==5,"conform|measure panel.txt output.json [reserved-slot]");std::string command=argv[1];require((command=="conform"&&argc==4)||(command=="measure"&&argc==5),"mode/slot mismatch");
        require(!std::filesystem::exists(argv[3]),"refuse output overwrite");const Panel p=read_panel(argv[2]);
        std::ofstream out(argv[3]);require(bool(out),"cannot create output");
        if(command=="conform")conform(out,p);else measure(out,p,argv[4]);require(bool(out),"output failure");return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
