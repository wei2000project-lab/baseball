"""Stateless ctypes ABI. No Python fallback for native physics."""
import ctypes as C
from build_native import LIB


class Native:
    def __init__(self):
        if not LIB.exists():
            raise RuntimeError("native_missing: run python workspace/build_native.py")
        self.lib = C.CDLL(str(LIB))
        self.lib.bb_numeric.argtypes = [C.c_int, C.c_int64, C.c_int64, C.POINTER(C.c_int64)]
        self.lib.bb_numeric.restype = C.c_int
        if self.lib.bb_abi() != 1:
            raise RuntimeError("native_abi_mismatch")

    def numeric(self, op, a, b=0):
        result = C.c_int64()
        if self.lib.bb_numeric(op, int(a), int(b), C.byref(result)):
            raise ValueError("native_numeric_error")
        return str(result.value)
