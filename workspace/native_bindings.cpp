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
