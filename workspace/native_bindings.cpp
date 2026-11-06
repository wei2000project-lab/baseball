#include "baseball.hpp"
#include "map.hpp"
#include <cstring>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
API int bb_numeric(int op, int64_t a, int64_t b, int64_t* out) {
    try { *out=op==0?bb::mul(a,b):op==1?bb::div(a,b):bb::root(bb::Wide(a)*bb::ONE); return 0; }
    catch(...) { return -1; }
}
API int bb_abi() { return 1; }
static bb::Vec vec(const int64_t* p) { return {p[0],p[1],p[2]}; }
static void write_vec(int64_t* out,bb::Vec v) { out[0]=v.x;out[1]=v.y;out[2]=v.z; }
API int bb_action(int kind,const int64_t* input,const int64_t* speeds,int64_t* out) {
    try {
        write_vec(out,bb::action_velocity(kind,vec(input),input[3],input[4],input[5],speeds[0],speeds[1],out+3));
        for(int i=0;i<3;i++)out[6+i]=bb::clamp(input[i],-1000000,1000000);
        return 0;
    } catch(...) { return -1; }
}
API int bb_contact(const int64_t* input,const int64_t* config,int64_t* out) {
    try { write_vec(out,bb::contact_velocity(input,config,out+3));return 0; }
    catch(...) {return -1;}
}
API int bb_field_skill(int op,const int64_t* input,const int64_t* c,int64_t* out) {
    try {
        using namespace bb;
        Vec running={input[0],input[1],0},ball=vec(input+2);
        Q speed=magnitude(running),fraction=clamp(bb::div(speed,c[0]),0,ONE);
        if(op==0) {
            out[0]=mul(c[1],ONE-mul(c[2],mul(fraction,fraction)))+(input[5]?c[5]:0);
            Q limit=c[3]-mul(c[4],speed)+(input[5]?c[6]:0);
            out[1]=magnitude(sub(ball,running))<=limit;
            out[2]=limit;out[3]=magnitude(sub(ball,running));
        } else if(op==1)write_vec(out,normalize(add(ball,scale(running,c[7])),magnitude(ball)));
        else if(op==2)write_vec(out,add(scale(ball,c[8]),scale(running,ONE/5)));
        else return -1;
        return 0;
    } catch(...) {return -1;}
}
API int bb_pitch_scatter(const int64_t* input,const int64_t* c,int64_t* out) {
    try {
        using namespace bb;
        Vec v=vec(input);Q speed=magnitude(v);
        Q fraction=c[0]==c[1]?ONE:clamp(bb::div(speed-c[0],c[1]-c[0]),0,ONE);
        Q envelope=mul(c[2],mul(fraction,fraction));
        // A public six-pitch release pattern, not an unseeded/random accuracy roll.
        Q phase=input[4]%6;Q signs[6]={-3,1,2,-1,3,-2};
        Q ex=checked(Wide(envelope)*signs[phase]/3);
        Q ez=checked(Wide(envelope)*signs[(phase*5+1)%6]/3);
        Q time=bb::div(input[3],-v.y);
        Vec scattered=normalize({v.x+bb::div(ex,time),v.y,v.z+bb::div(ez,time)},speed);
        write_vec(out,scattered);out[3]=ex;out[4]=ez;out[5]=envelope;return 0;
    }catch(...) {return -1;}
}
API int64_t bb_sweep_box(const int64_t* from,const int64_t* to,const int64_t* box,int64_t radius) {
    try { return bb::sweep_box(vec(from),vec(to),box,radius); }catch(...) { return -2; }
}
API int64_t bb_sweep_cylinder(const int64_t* from,const int64_t* to,const int64_t* pa,const int64_t* pb,int64_t radius,int64_t height) {
    try { return bb::sweep_cylinder(vec(from),vec(to),vec(pa),vec(pb),radius,height); }catch(...) { return -2; }
}
API int bb_flight(const int64_t* input,const int64_t* config,int64_t* out) {
    try {
        bb::Physics c={config[0],config[1],config[2],config[3],config[4],config[5],config[6],
            config[7],config[8],config[9],config[10],config[11],config[12],config[13]};
        auto f=bb::advance_ball(vec(input),vec(input+3),input[6],input[7],input[8],c);
        write_vec(out,f.position);write_vec(out+3,f.velocity);out[6]=f.consumed;out[7]=f.event;out[8]=f.rolling;
        write_vec(out+9,f.flight_velocity);
        return 0;
    }catch(...) { return -1; }
}
API int bb_move(const int64_t* input,int64_t* out) {
    try {
        auto m=bb::move_player({input[0],input[1],0},{input[2],input[3],0},{input[4],input[5],0},
            input[6],input[7],input[8],input[9],input[10]);
        out[0]=m.end.x;out[1]=m.end.y;out[2]=m.velocity.x;out[3]=m.velocity.y;out[4]=m.touch;out[5]=m.stopped;
        return 0;
    }catch(...) { return -1; }
}
API int bb_field(int64_t x,int64_t y,int64_t radius) { return bb::fair(x,y,radius); }
API int bb_lerp(const int64_t* from,const int64_t* to,int64_t time,int64_t* out) {
    try { write_vec(out,bb::lerp(vec(from),vec(to),time));return 0; }catch(...) { return -1; }
}
API int bb_strike(const int64_t* at,const int64_t* zone,int64_t radius) {
    bb::Q x=at[0],z=at[2];
    bb::Q dx=x<zone[0]?zone[0]-x:x>zone[1]?x-zone[1]:0;
    bb::Q dz=z<zone[2]?zone[2]-z:z>zone[3]?z-zone[3]:0;
    return bb::Wide(dx)*dx+bb::Wide(dz)*dz<=bb::Wide(radius)*radius;
}
API int bb_clamp_position(const int64_t* at,const int64_t* bounds,int64_t* out) {
    out[0]=bb::clamp(at[0],bounds[0],bounds[1]);out[1]=bb::clamp(at[1],bounds[2],bounds[3]);return 0;
}
API int64_t bb_progress(const int64_t* at,const int64_t* a,const int64_t* b) {
    try {return bb::path_progress(vec(at),vec(a),vec(b));}catch(...) {return -1;}
}
API int bb_clamp_position_v2(const int64_t* at,const int64_t* bounds,int64_t* out) {
    try {auto p=bb::legal_position({at[0],at[1],0},bounds);out[0]=p.x;out[1]=p.y;return 0;}catch(...) {return -1;}
}
API int bb_move_fielder(const int64_t* input,const int64_t* bounds,int64_t* out) {
    try {
        auto m=bb::move_fielder({input[0],input[1],0},{input[2],input[3],0},{input[4],input[5],0},input[6],input[8],input[9],input[10],bounds);
        out[0]=m.end.x;out[1]=m.end.y;out[2]=m.velocity.x;out[3]=m.velocity.y;out[4]=m.touch;out[5]=m.stopped;return 0;
    }catch(...) {return -1;}
}
