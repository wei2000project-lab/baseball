#pragma once
#include <cstdint>
#include <stdexcept>
#include <limits>

namespace bb {
using Q = int64_t;
using Wide = __int128;
constexpr Q ONE = Q(1) << 32;
inline Q checked(Wide n) {
    if(n > std::numeric_limits<Q>::max() || n < std::numeric_limits<Q>::min())
        throw std::overflow_error("numeric_overflow");
    return Q(n);
}
inline Q mul(Q a, Q b) { return checked(Wide(a)*b/ONE); }
inline Q div(Q a, Q b) {
    if(!b) throw std::runtime_error("division_by_zero");
    return checked(Wide(a)*ONE/b);
}
inline Q root(Wide n) {
    if(n < 0) throw std::runtime_error("negative_root");
    Wide lo=0, hi=Wide(1)<<64;
    while(lo+1<hi) { Wide m=(lo+hi)/2; if(m*m<=n) lo=m; else hi=m; }
    return checked(lo);
}
struct Vec { Q x, y, z; };
inline Q clamp(Q n, Q lo, Q hi) { return n<lo?lo:n>hi?hi:n; }
inline Q magnitude(Vec v) { return root(Wide(v.x)*v.x+Wide(v.y)*v.y+Wide(v.z)*v.z); }
inline Vec scale(Vec v, Q n) { return {mul(v.x,n),mul(v.y,n),mul(v.z,n)}; }
inline Vec add(Vec a, Vec b) { return {checked(Wide(a.x)+b.x),checked(Wide(a.y)+b.y),checked(Wide(a.z)+b.z)}; }
inline Vec sub(Vec a, Vec b) { return {checked(Wide(a.x)-b.x),checked(Wide(a.y)-b.y),checked(Wide(a.z)-b.z)}; }
inline Vec lerp(Vec a, Vec b, Q t) { return add(a,scale(sub(b,a),t)); }
inline bool world(Vec p, Q bound=1000*ONE) { return p.x>=-bound&&p.x<=bound&&p.y>=-bound&&p.y<=bound&&p.z>=-bound&&p.z<=bound; }

// Integer CORDIC, angles in millidegrees. 31 atan constants in binary turns
// (one full turn = 2^32). Versioned constants; no platform libm calls.
void sincos(int64_t millidegrees, Q& sine, Q& cosine);
Vec normalize(Vec direction, Q speed);
Vec action_velocity(int kind, Vec direction, int64_t power, int64_t azimuth, int64_t elevation,
                    Q min_speed, Q max_speed, int64_t* normalized);
// Sweep time is Q0.32, -1 = no contact. Geometry includes boundaries.
Q sweep_box(Vec a, Vec b, const Q* box, Q radius);
Q sweep_cylinder(Vec a, Vec b, Vec player_a, Vec player_b, Q radius, Q height);
struct Physics {
    Q gravity, radius, restitution, retention, friction, stop, rolling_threshold;
    Q wall_radius, wall_height, wall_restitution, xmin, xmax, ymin, ymax;
};
struct Flight {
    Vec position, velocity;
    Q consumed;
    int event; // 0 none, 1 ground, 2 wall, 3 out of play
    int rolling;
    Vec flight_velocity;
};
Flight advance_ball(Vec p, Vec v, Q remaining, bool rolling, bool apply_forces, const Physics& c);
}
