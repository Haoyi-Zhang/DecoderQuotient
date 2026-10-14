"""Bounded CUDA Driver API realization of the two decoder arithmetic arms.

The caller owns the input-domain admission and experimental protocol. No GPU
code is executed by import or by the portable retained-record checker.
"""
from __future__ import annotations

import ctypes as c
import ctypes.util
from pathlib import Path
import platform
import time


class DecoderDevice:
    MAX_WORDS = 65536
    SENTINEL = 0xD31B7A59

    def __init__(self, ptx: Path):
        library = ("C:/Windows/System32/nvcuda.dll" if platform.system() == "Windows"
                   else ctypes.util.find_library("cuda"))
        if not library:
            raise RuntimeError("CUDA driver library is unavailable")
        self.d = (c.WinDLL if platform.system() == "Windows" else c.CDLL)(library)
        self.ctx, self.module = c.c_void_p(), c.c_void_p()
        self.allocations, self.events, self.functions = [], [], {}
        p, v = c.POINTER, c.c_void_p
        bindings = {
            "cuInit": [c.c_uint], "cuDriverGetVersion": [p(c.c_int)],
            "cuDeviceGet": [p(c.c_int), c.c_int],
            "cuDeviceGetName": [v, c.c_int, c.c_int],
            "cuDeviceGetAttribute": [p(c.c_int), c.c_int, c.c_int],
            "cuDeviceTotalMem_v2": [p(c.c_size_t), c.c_int],
            "cuCtxCreate_v2": [p(v), c.c_uint, c.c_int], "cuCtxDestroy_v2": [v],
            "cuModuleLoadDataEx": [p(v), v, c.c_uint, p(c.c_uint), p(v)],
            "cuModuleGetFunction": [p(v), v, c.c_char_p], "cuModuleUnload": [v],
            "cuMemAlloc_v2": [p(c.c_uint64), c.c_size_t],
            "cuMemFree_v2": [c.c_uint64],
            "cuMemcpyHtoD_v2": [c.c_uint64, v, c.c_size_t],
            "cuMemcpyDtoH_v2": [v, c.c_uint64, c.c_size_t],
            "cuCtxSynchronize": [],
            "cuLaunchKernel": [v] + [c.c_uint] * 7 + [v, p(v), p(v)],
            "cuEventCreate": [p(v), c.c_uint], "cuEventDestroy_v2": [v],
            "cuEventRecord": [v, v], "cuEventSynchronize": [v],
            "cuEventElapsedTime": [p(c.c_float), v, v],
        }
        for name, args in bindings.items():
            fn = getattr(self.d, name)
            fn.argtypes, fn.restype = args, c.c_int
        try:
            start = time.perf_counter_ns()
            self.call("cuInit", 0)
            device = c.c_int()
            self.call("cuDeviceGet", c.byref(device), 0)
            version, total = c.c_int(), c.c_size_t()
            name = c.create_string_buffer(256)
            self.call("cuDriverGetVersion", c.byref(version))
            self.call("cuDeviceGetName", name, len(name), device)
            self.call("cuDeviceTotalMem_v2", c.byref(total), device)
            attributes = {}
            for label, index in (("compute_major", 75), ("compute_minor", 76),
                                 ("multiprocessors", 16)):
                value = c.c_int()
                self.call("cuDeviceGetAttribute", c.byref(value), index, device)
                attributes[label] = value.value
            if (attributes["compute_major"], attributes["compute_minor"]) < (6, 1):
                raise ValueError("This PTX realization targets compute capability 6.1 or later")
            self.info = dict(name=name.value.decode(), driver_api=version.value,
                             total_device_bytes=total.value, **attributes)
            self.call("cuCtxCreate_v2", c.byref(self.ctx), 0, device)
            self.context_ns = time.perf_counter_ns() - start
            source = c.create_string_buffer(ptx.read_bytes())
            error = c.create_string_buffer(4096)
            options = (c.c_uint * 2)(5, 6)
            values = (v * 2)(c.cast(error, v), v(len(error)))
            start = time.perf_counter_ns()
            code = self.d.cuModuleLoadDataEx(c.byref(self.module), source, 2, options, values)
            if code:
                raise RuntimeError(f"CUDA JIT error {code}: {error.value.decode(errors='replace')}")
            self.module_load_ns = time.perf_counter_ns() - start
            for arm in ("packed", "lane"):
                function = v()
                self.call("cuModuleGetFunction", c.byref(function), self.module,
                          (arm + "_decoder").encode())
                self.functions[arm] = function
            for _ in range(2):
                address = c.c_uint64()
                self.call("cuMemAlloc_v2", c.byref(address), (self.MAX_WORDS + 2) * 4)
                self.allocations.append(address)
            for _ in range(2):
                event = v()
                self.call("cuEventCreate", c.byref(event), 0)
                self.events.append(event)
        except BaseException:
            self.close()
            raise

    def call(self, name, *args):
        code = getattr(self.d, name)(*args)
        if code:
            raise RuntimeError(f"{name}: CUDA error {code}")

    def run(self, words, scale, bias, arm):
        if (type(scale) is not int or not 0 <= scale <= 255 or
                type(bias) is not int or not 0 <= bias <= 0xFFFFFFFF or
                arm not in self.functions or not 1 <= len(words) <= self.MAX_WORDS or
                any(type(x) is not int or not 0 <= x <= 0xFFFFFFFF for x in words)):
            raise ValueError("Invalid bounded decoder invocation")
        if not self.ctx:
            raise RuntimeError("CUDA device context is closed")
        host = (c.c_uint32 * len(words))(*words)
        output = (c.c_uint32 * (len(words) + 2))(*([self.SENTINEL] * (len(words) + 2)))
        start = time.perf_counter_ns()
        self.call("cuMemcpyHtoD_v2", self.allocations[0], host, c.sizeof(host))
        self.call("cuMemcpyHtoD_v2", self.allocations[1], output, c.sizeof(output))
        arguments = [self.allocations[0], c.c_uint64(self.allocations[1].value + 4),
                     c.c_uint32(len(words)), c.c_uint32(scale), c.c_uint32(bias)]
        arg_array = (c.c_void_p * len(arguments))(
            *(c.cast(c.byref(a), c.c_void_p) for a in arguments))
        self.call("cuEventRecord", self.events[0], None)
        self.call("cuLaunchKernel", self.functions[arm], (len(words) + 127) // 128,
                  1, 1, 128, 1, 1, 0, None, arg_array, None)
        self.call("cuEventRecord", self.events[1], None)
        self.call("cuEventSynchronize", self.events[1])
        elapsed = c.c_float()
        self.call("cuEventElapsedTime", c.byref(elapsed), *self.events)
        self.call("cuMemcpyDtoH_v2", output, self.allocations[1], c.sizeof(output))
        call_ns = time.perf_counter_ns() - start
        if output[0] != self.SENTINEL or output[-1] != self.SENTINEL:
            raise RuntimeError("GPU decoder overwrote an output guard")
        return list(output)[1:-1], {"event_ms": elapsed.value, "transfer_call_ns": call_ns}

    def close(self):
        # Attempt all releases even when a previous asynchronous call failed.
        errors = []
        for name, objects in (("cuEventDestroy_v2", self.events),
                              ("cuMemFree_v2", self.allocations)):
            for obj in objects:
                try:
                    self.call(name, obj)
                except RuntimeError as exc:
                    errors.append(str(exc))
            objects.clear()
        for name, obj in (("cuModuleUnload", self.module), ("cuCtxDestroy_v2", self.ctx)):
            if obj:
                try:
                    self.call(name, obj)
                except RuntimeError as exc:
                    errors.append(str(exc))
                obj.value = None
        if errors:
            raise RuntimeError("; ".join(errors))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
