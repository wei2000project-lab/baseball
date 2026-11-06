#pragma once
#include "baseball.hpp"
namespace bb {
bool fair(Q x, Q y, Q radius);
struct Movement { Vec end, velocity; Q touch; bool stopped; };
Movement move_player(Vec p, Vec v, Vec target, bool moving, bool stop_on_touch,
                     Q speed, Q acceleration, Q touch_radius);
Q path_progress(Vec p,Vec a,Vec b);
}
