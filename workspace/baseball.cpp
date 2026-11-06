#include "baseball.hpp"
#include "map.hpp"

namespace bb {
static Q ratio(Q n,Q d) {
    if(!d)throw std::runtime_error("division_by_zero");
    Wide value=Wide(n)*ONE/d;
    return value<-Wide(ONE)?-ONE:value>Wide(2)*ONE?2*ONE:Q(value);
}
void sincos(int64_t angle, Q& sine, Q& cosine) {
    if(angle==0) { sine=0;cosine=ONE;return; }
    static const Q atan_turns[31]={536870912,316933406,167458907,85004756,42667331,21354465,
        10679838,5340245,2670163,1335087,667544,333772,166886,83443,41722,20861,
        10430,5215,2608,1304,652,326,163,81,41,20,10,5,3,1,1};
    Q z=checked(Wide(angle)*ONE/360000), x=2608131496LL, y=0;
    for(int i=0;i<31;i++) {
        Q d=z>=0?1:-1, denom=Q(1)<<i;
        Q nx=x-d*(y/denom), ny=y+d*(x/denom);
        x=nx; y=ny; z-=d*atan_turns[i];
    }
    sine=y; cosine=x;
}
Vec normalize(Vec d, Q speed) {
    Q length=magnitude(d);
    if(!length) throw std::runtime_error("zero_direction");
    Vec out={checked(Wide(d.x)*speed/length),checked(Wide(d.y)*speed/length),checked(Wide(d.z)*speed/length)};
    if(Wide(out.x)*out.x+Wide(out.y)*out.y+Wide(out.z)*out.z>Wide(speed)*speed) {
        ++length;out={checked(Wide(d.x)*speed/length),checked(Wide(d.y)*speed/length),checked(Wide(d.z)*speed/length)};
    }
    return out;
}
Vec action_velocity(int kind, Vec d, int64_t power, int64_t azimuth, int64_t elevation,
                    Q min_speed, Q max_speed, int64_t* n) {
    if(power<INT32_MIN||power>INT32_MAX||azimuth<INT32_MIN||azimuth>INT32_MAX||elevation<INT32_MIN||elevation>INT32_MAX)
        throw std::runtime_error("action_integer_range");
    n[0]=clamp(power,0,65535); n[1]=clamp(azimuth,-80000,80000); n[2]=clamp(elevation,-15000,75000);
    Q speed=min_speed+checked(Wide(max_speed-min_speed)*n[0]/65535);
    if(kind==2) {
        Q sa,ca,se,ce; sincos(n[1],sa,ca); sincos(n[2],se,ce);
        d={mul(sa,ce),mul(ca,ce),se};
    } else {
        if(!world(d,INT32_MAX)) throw std::runtime_error("direction_integer_range");
        d.x=clamp(d.x,-1000000,1000000); d.y=clamp(d.y,-1000000,1000000); d.z=clamp(d.z,-1000000,1000000);
        // Convert bounded direction integers to Q32.32 before normalization.
        d={checked(Wide(d.x)*ONE),checked(Wide(d.y)*ONE),checked(Wide(d.z)*ONE)};
    }
    return normalize(d,speed);
}

Vec contact_velocity(const Q* in, const Q* c, Q* quality) {
    // in: power, azimuth, elevation, elapsed ticks (Q), duration (Q), x, z.
    // c: min/max speed, narrowing, timing loss, spatial loss, speed floor,
    //    box x centre/half width, z centre/half height, deflection millidegrees.
    Q power=clamp(in[0],0,65535);
    Q half=clamp(mul(in[4]/2,ONE-checked(Wide(c[2])*power/65535)),ONE/8,1000*ONE);
    Q t=clamp(div(in[3]-in[4]/2,half),-ONE,ONE);
    Q x=clamp(div(in[5]-c[6],c[7]),-ONE,ONE);
    Q z=clamp(div(in[6]-c[8],c[9]),-ONE,ONE);
    Q qt=ONE-mul(c[3],mul(t,t));
    Q qp=clamp(ONE-mul(c[4],mul(x,x)+mul(z,z)),0,ONE);
    *quality=mul(qt,qp);
    Q factor=c[5]+mul(ONE-c[5],*quality);
    Q speed=mul(c[0]+checked(Wide(c[1]-c[0])*power/65535),factor);
    Q az=clamp(in[1]+checked(Wide(c[10])*(t+x)/ONE),-80000,80000);
    Q el=clamp(in[2]+checked(Wide(c[10])*z/ONE),-15000,75000);
    Q n[3];return action_velocity(2,{0,0,0},65535,az,el,speed,speed,n);
}

Q sweep_box(Vec a, Vec b, const Q* box, Q r) {
    Q starts[3]={a.x,a.y,a.z}, ends[3]={b.x,b.y,b.z}, enter=0, leave=ONE;
    for(int i=0;i<3;i++) {
        Q lo=box[2*i]-r, hi=box[2*i+1]+r, d=ends[i]-starts[i];
        if(!d) { if(starts[i]<lo||starts[i]>hi) return -1; continue; }
        Q u=ratio(lo-starts[i],d), v=ratio(hi-starts[i],d);
        if(u>v) { Q tmp=u;u=v;v=tmp; }
        if(u>enter) enter=u;
        if(v<leave) leave=v;
        if(enter>leave) return -1;
    }
    return enter<=ONE&&leave>=0?clamp(enter,0,ONE):-1;
}

// 128 x 128 unsigned multiply, used only for exact squared-distance comparison.
// Four 64-bit words avoid discarding low coordinate bits in tangency tests.
struct U256 { uint64_t w[4]; };
static U256 product(unsigned __int128 a, unsigned __int128 b) {
    uint64_t av[2]={uint64_t(a),uint64_t(a>>64)},bv[2]={uint64_t(b),uint64_t(b>>64)};
    U256 out={{0,0,0,0}};
    for(int i=0;i<2;i++) for(int j=0;j<2;j++) {
        unsigned __int128 p=(unsigned __int128)av[i]*bv[j];
        int k=i+j; unsigned __int128 sum=(unsigned __int128)out.w[k]+uint64_t(p);
        out.w[k]=uint64_t(sum); unsigned __int128 carry=(p>>64)+(sum>>64);
        while(carry&&++k<4) { sum=(unsigned __int128)out.w[k]+uint64_t(carry); out.w[k]=uint64_t(sum);carry=(carry>>64)+(sum>>64); }
    }
    return out;
}
static bool le(U256 a,U256 b) { for(int i=3;i>=0;i--) { if(a.w[i]!=b.w[i])return a.w[i]<b.w[i]; }return true; }
static Wide square2(Vec p) { return Wide(p.x)*p.x+Wide(p.y)*p.y; }
Q sweep_cylinder(Vec a, Vec b, Vec pa, Vec pb, Q r, Q h) {
    // Relative moving glove, with fixed logical height. z is absolute ball height.
    Vec s={a.x-pa.x,a.y-pa.y,a.z}, e={b.x-pb.x,b.y-pb.y,b.z}, d=sub(e,s);
    Q zbox[6]={-2000*ONE,2000*ONE,-2000*ONE,2000*ONE,0,h};
    Q lower=sweep_box(s,e,zbox,0);
    if(lower<0) return -1;
    Q upper=ONE;
    if(d.z>0) upper=clamp(ratio(h-s.z,d.z),0,ONE);
    else if(d.z<0) upper=clamp(ratio(-s.z,d.z),0,ONE);
    if(lower>upper)return -1;
    Wide rr=Wide(r)*r;
    if(square2(lerp(s,e,lower))<=rr) return lower;
    Wide A=square2(d), dot=Wide(s.x)*d.x+Wide(s.y)*d.y;
    if(!A) return -1;
    Q closest=clamp(checked((-dot*ONE)/A),lower,upper);
    bool exists=square2(lerp(s,e,closest))<=rr;
    if(!exists&&closest>lower&&closest<upper) {
        Wide cross=Wide(s.x)*d.y-Wide(s.y)*d.x;
        auto cross_abs=(unsigned __int128)(cross<0?-cross:cross);
        exists=le(product(cross_abs,cross_abs),product((unsigned __int128)rr,(unsigned __int128)A));
    }
    if(!exists) return -1;
    Q lo=lower, hi=closest;
    while(lo+1<hi) { Q m=(lo+hi)/2; if(square2(lerp(s,e,m))<=rr) hi=m; else lo=m; }
    // First entry rounded down in Q0.32. Exact representable boundary is retained.
    return square2(lerp(s,e,hi))==rr?hi:lo;
}

static Q circle_exit(Vec a, Vec b, Q radius) {
    if(square2(b)<Wide(radius)*radius) return -1;
    Q lo=0,hi=ONE;
    while(lo+1<hi) { Q m=(lo+hi)/2; if(square2(lerp(a,b,m))>=Wide(radius)*radius)hi=m;else lo=m; }
    return hi;
}
Flight advance_ball(Vec p, Vec v, Q remaining, bool rolling, bool forces, const Physics& c) {
    if(!world(p)||!world(v,100*ONE)||remaining<0||remaining>ONE)throw std::runtime_error("physical_range");
    if(forces) {
        if(!rolling) v.z-=c.gravity/120;
        else {
            v.z=0; Q speed=magnitude(v), next=speed-c.friction/120;
            v=next<c.stop?Vec{0,0,0}:normalize(v,next);
        }
    }
    Vec flight_velocity=v;
    Vec delta={checked(Wide(v.x)*remaining/(120*Wide(ONE))),checked(Wide(v.y)*remaining/(120*Wide(ONE))),checked(Wide(v.z)*remaining/(120*Wide(ONE)))};
    Vec end=add(p,delta); Q time=ONE; int event=0;
    auto candidate=[&](Q t,int kind) { if(t>=0&&t<=ONE&&(t<time||(t==time&&(event==0||kind<event)))) { time=t;event=kind; } };
    if(!rolling&&v.z<0&&end.z<=c.radius)candidate(p.z<=c.radius?0:div(c.radius-p.z,end.z-p.z),1);
    Q wall=circle_exit(p,end,c.wall_radius);
    if(wall>=0) {
        Vec at=lerp(p,end,wall);
        if(fair(at.x,at.y,c.radius))candidate(wall,(at.z-c.radius>c.wall_height)?3:2);
    }
    if(end.x<c.xmin&&delta.x<0)candidate(div(c.xmin-p.x,delta.x),3);
    if(end.x>c.xmax&&delta.x>0)candidate(div(c.xmax-p.x,delta.x),3);
    if(end.y<c.ymin&&delta.y<0)candidate(div(c.ymin-p.y,delta.y),3);
    if(end.y>c.ymax&&delta.y>0)candidate(div(c.ymax-p.y,delta.y),3);
    Vec at=lerp(p,end,time);
    Q consumed=mul(remaining,time);
    if(event==1) {
        at.z=c.radius;v.z=-mul(v.z,c.restitution);v.x=mul(v.x,c.retention);v.y=mul(v.y,c.retention);
        if(v.z<c.rolling_threshold) { rolling=true;v.z=0; }
    } else if(event==2) {
        Vec normal=normalize({at.x,at.y,0},ONE);
        Q dot=mul(v.x,normal.x)+mul(v.y,normal.y);
        Q impulse=mul(ONE+c.wall_restitution,dot);
        v.x-=mul(impulse,normal.x);v.y-=mul(impulse,normal.y);
        Vec inside=scale(normal,c.wall_radius-1);at.x=inside.x;at.y=inside.y;
    }
    return {at,v,consumed,event,int(rolling),flight_velocity};
}
}
