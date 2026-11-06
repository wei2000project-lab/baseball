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
}
