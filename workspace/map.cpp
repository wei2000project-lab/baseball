#include "map.hpp"
namespace bb {
bool fair(Q x, Q y, Q radius) { return y+radius>=0 && x<=y+radius && -x<=y+radius; }
}
