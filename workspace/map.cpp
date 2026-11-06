#include "map.hpp"
namespace bb {
bool fair(Q x, Q y, Q radius) { return y+radius>=0 && x<=y+radius && -x<=y+radius; }
Movement move_player(Vec p,Vec v,Vec target,bool moving,bool stop_on_touch,Q speed,Q acceleration,Q radius) {
    p.z=v.z=target.z=0;
    if(!world(p)||!world(target)||!world(v,100*ONE))throw std::runtime_error("movement_range");
    Vec desired={0,0,0},diff=sub(target,p);
    Q distance=magnitude(diff);
    if(moving&&distance) desired=normalize(diff,speed);
    Vec change=sub(desired,v);Q change_length=magnitude(change),limit=acceleration/120;
    if(change_length>limit)change=normalize(change,limit);
    v=add(v,change);Vec end=add(p,{v.x/120,v.y/120,0});
    Q touch=moving?sweep_cylinder(p,end,target,target,radius,ONE):-1;
    bool stopped=false;
    if(moving&&touch>=0&&stop_on_touch) {
        end=lerp(p,end,touch);
        // The contact time is rounded down; keep the committed stop inside the
        // closed touch region instead of stranding it one coordinate quantum out.
        Vec offset=sub(end,target);
        end=radius>16&&magnitude(offset)>radius-16?add(target,normalize(offset,radius-16)):end;
        if(radius==0)end=target;
        v={0,0,0};stopped=true;
    }
    // General movement targets stop at their center, runners use base touch radius.
    return {end,v,touch,stopped};
}
Q path_progress(Vec p,Vec a,Vec b) {
    Vec d=sub(b,a),s=sub(p,a);
    Wide norm=Wide(d.x)*d.x+Wide(d.y)*d.y;
    if(!norm)throw std::runtime_error("invalid_path_segment");
    Wide dot=Wide(s.x)*d.x+Wide(s.y)*d.y;
    if(dot<=0)return 0;
    if(dot>=norm)return ONE;
    return checked(dot*ONE/norm);
}
Vec legal_position(Vec p,const Q* b) {
    p.x=clamp(p.x,b[0],b[1]);p.y=clamp(p.y,b[2],b[3]);p.z=0;
    if(fair(p.x,p.y,0)&&Wide(p.x)*p.x+Wide(p.y)*p.y>Wide(b[4])*b[4])
        p=normalize(p,b[4]-16);
    return p;
}
Movement move_fielder(Vec p,Vec v,Vec target,bool moving,Q speed,Q acceleration,Q radius,const Q* bounds) {
    p.z=v.z=target.z=0;
    if(!world(p)||!world(target)||!world(v,100*ONE))throw std::runtime_error("movement_range");
    target=legal_position(target,bounds);
    Vec diff=sub(target,p),desired={0,0,0};Q distance=magnitude(diff);
    if(moving&&distance>radius) {
        // Brake before an ordinary target; only runners get the hard-stop exception.
        Q braking=root(Wide(2)*acceleration*(distance-radius));
        desired=normalize(diff,braking<speed?braking:speed);
    }
    Vec change=sub(desired,v);Q limit=acceleration/120;
    if(magnitude(change)>limit)change=normalize(change,limit);
    v=add(v,change);Vec end=add(p,{v.x/120,v.y/120,0});
    Vec legal=legal_position(end,bounds);
    if(legal.x!=end.x||legal.y!=end.y) {
        Q lo=0,hi=ONE;
        while(lo+1<hi){Q t=(lo+hi)/2;Vec at=lerp(p,end,t),ok=legal_position(at,bounds);if(at.x==ok.x&&at.y==ok.y)lo=t;else hi=t;}
        end=legal_position(lerp(p,end,hi),bounds);v={0,0,0};
        return {end,v,hi,true}; // boundary collision, with a piecewise stop time
    }
    Vec gap=sub(end,target);
    bool stopped=moving&&Wide(gap.x)*gap.x+Wide(gap.y)*gap.y<=Wide(radius)*radius&&v.x==0&&v.y==0;
    Q touch=moving?sweep_cylinder(p,end,target,target,radius,ONE):-1;
    return {end,v,touch,stopped};
}
}
