"""Generate or independently consume bounded, paired GPU decoder evidence.

The retained-record consumer uses no CUDA library. The run command requires an
actual compatible device and never substitutes CPU outputs for GPU execution.
"""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bptc.certificate_format import exact, strict_json_loads
from bptc.packed_decoder import check_decoder_certificate, spec_to_dict
from bptc.publication_budget import ObligationLedger
from bptc.publication_cases import decoder_specs

SIZES = (4096, 65536)
PAIRS = 15
BOUND_SOURCES = ("native/cuda_decoder_driver.py", "native/decoder_gpu.ptx",
                 "native/gpu_decoder_study.py", "bptc/packed_decoder.py",
                 "bptc/publication_cases.py", "bptc/certificate_format.py",
                 "bptc/publication_budget.py", "inputs/omniserve/share_to_reg_one_stage_B.cu")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def words_for(spec):
    return [sum(digit << (8 * lane) for lane, digit in enumerate(digits))
            for digits in product(*(range(maximum + 1) for maximum in spec.maxima))]


def reference_outputs(spec, words):
    # Whole-word multiplication and independently evaluated lanes; neither
    # expression calls the carry producer, the replay checker or device code.
    packed, lane = [], []
    for word in words:
        multiplied = (word * spec.scale) % (1 << 32)
        packed.append(sum((((multiplied >> (8 * i)) % 256 + spec.biases[i]) % 256)
                          << (8 * i) for i in range(4)))
        lane.append(sum(((((word >> (8 * i)) % 256 * spec.scale + spec.biases[i]) % 256)
                        << (8 * i)) for i in range(4)))
    return packed, lane


def certificates():
    ledger = ObligationLedger(200000)
    result = {}
    for spec in decoder_specs():
        path = ROOT / "results/publication/main/decoder-certificates" / (spec.name + ".json")
        record = strict_json_loads(path.read_text(encoding="utf-8"))
        exact(record["spec"], spec_to_dict(spec), "declared GPU box")
        check_decoder_certificate(record, ledger)
        result[spec.name] = record
    return result, ledger.to_dict()


def bindings():
    paths = list(BOUND_SOURCES) + ["results/publication/main/decoder-certificates/" + spec.name + ".json"
                                  for spec in decoder_specs()]
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def cpu_model():
    if platform.system() == "Windows":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or None


def encode_words(values):
    result = array("I", values)
    require(result.itemsize == 4, "32-bit array representation unavailable")
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def decode_words(data):
    require(len(data) % 4 == 0, "Truncated GPU output word")
    result = array("I")
    result.frombytes(data)
    require(result.itemsize == 4, "32-bit array representation unavailable")
    if sys.byteorder != "little":
        result.byteswap()
    return list(result)


def case_record(spec, words, packed, lane, safe, offset):
    different = [i for i, (left, right) in enumerate(zip(packed, lane)) if left != right]
    first = different[0] if different else None
    return {"spec": spec_to_dict(spec), "words": len(words), "byte_offset": offset,
            "admitted_equivalent": safe, "unequal_words": len(different),
            "least_counterexample_digits": None if first is None else
                [(words[first] >> (8 * i)) & 255 for i in range(4)]}


def sample_valid(record):
    require(type(record) is dict and set(record) == {"event_ms", "transfer_call_ns"},
            "Invalid GPU interval fields")
    event = record["event_ms"]
    require(type(event) in (int, float) and math.isfinite(event) and event > 0,
            "GPU event interval must be positive and finite")
    require(type(record["transfer_call_ns"]) is int and record["transfer_call_ns"] > 0,
            "Host transfer/call interval must be a positive integer")


def summarize(timings):
    groups = []
    for name in sorted({row["name"] for row in timings}):
        for size in SIZES:
            rows = [row for row in timings if row["name"] == name and row["words"] == size]
            require(len(rows) == PAIRS, "Incomplete GPU paired case")
            groups.append({"name": name, "words": size,
                "event_lane_over_packed": statistics.median(
                    row["lane"]["event_ms"] / row["packed"]["event_ms"] for row in rows),
                "transfer_call_lane_over_packed": statistics.median(
                    row["lane"]["transfer_call_ns"] / row["packed"]["transfer_call_ns"] for row in rows)})
    return {"per_case": groups, "pairs": len(timings),
            "event_case_ratio_median": statistics.median(row["event_lane_over_packed"] for row in groups),
            "transfer_call_case_ratio_median": statistics.median(row["transfer_call_lane_over_packed"] for row in groups),
            "event_case_ratio_range": [min(row["event_lane_over_packed"] for row in groups),
                                       max(row["event_lane_over_packed"] for row in groups)],
            "transfer_call_case_ratio_range": [min(row["transfer_call_lane_over_packed"] for row in groups),
                                               max(row["transfer_call_lane_over_packed"] for row in groups)]}


def check(out):
    with (out / "study.json").open("rb") as stream:
        source = stream.read(2 * 1024 * 1024 + 1)
    require(len(source) <= 2 * 1024 * 1024, "GPU metadata exceeds the fixed record bound")
    record = strict_json_loads(source.decode("utf-8"))
    require(type(record) is dict and set(record) == {"format", "environment", "protocol", "source_bindings",
            "certificate_ledger", "cases", "timings", "warmups", "setup_costs", "summary"}, "Invalid study fields")
    require(record["format"] == "decoder-gpu-evidence", "Wrong evidence type")
    exact(record["source_bindings"], bindings(), "GPU source context")
    protocol = {"sizes": list(SIZES), "pairs_per_case": PAIRS, "block_threads": 128,
                "order": "packed-first on even pairs; lane-first on odd pairs",
                "event_interval": "one launch between default-stream events; includes scheduling and enqueue gaps",
                "transfer_call": "input copy, output poisoning, launch/event management, wait and complete guarded output copy",
                "excluded": "context/module setup, host fixture allocation, reference validation, log/statistic generation",
                "allocation_bytes": 2 * (65536 + 2) * 4,
                "timed_domain": "only certificate-admitted boxes; deterministic fixture cycling"}
    exact(record["protocol"], protocol, "GPU protocol")
    environment = record["environment"]
    require(type(environment) is dict and set(environment) == {"execution", "started_utc", "system", "machine",
            "python", "device", "clock_control", "host_affinity", "exclusive_device", "display_scheduling",
            "nvidia_smi", "cpu_model"} and environment["execution"] == "actual CUDA Driver API launches",
            "No actual-device execution declaration")
    for field in ("started_utc", "system", "machine", "python", "display_scheduling"):
        require(type(environment[field]) is str and bool(environment[field]), "Incomplete environment field")
    require(datetime.fromisoformat(environment["started_utc"]).utcoffset() is not None, "Missing execution timezone")
    exact(environment["exclusive_device"], False, "GPU sharing declaration")
    exact(environment["clock_control"], "not locked", "GPU clock declaration")
    exact(environment["host_affinity"], "not pinned", "GPU host-affinity declaration")
    for field in ("nvidia_smi", "cpu_model"):
        require(environment[field] is None or (type(environment[field]) is str and bool(environment[field])), "Invalid optional environment field")
    device = environment["device"]
    require(type(device) is dict and set(device) == {"name", "driver_api", "total_device_bytes", "compute_major", "compute_minor", "multiprocessors"}, "Invalid device identity")
    require(type(device["name"]) is str and bool(device["name"]), "Missing GPU model")
    for field in ("driver_api", "total_device_bytes", "compute_major", "compute_minor", "multiprocessors"):
        require(type(device[field]) is int and device[field] >= (0 if field == "compute_minor" else 1), "Invalid device field")
    require((device["compute_major"], device["compute_minor"]) >= (6, 1), "Unsupported GPU architecture")
    require(type(record["setup_costs"]) is dict and set(record["setup_costs"]) == {"context_ns", "module_load_ns", "certificate_check_ns", "device_setup_ns", "cache_state"},
            "Incomplete setup-cost fields")
    exact(record["setup_costs"]["cache_state"], "driver caches not purged", "GPU cache declaration")
    for field in ("context_ns", "module_load_ns", "certificate_check_ns", "device_setup_ns"):
        require(type(record["setup_costs"][field]) is int and record["setup_costs"][field] > 0, "Invalid setup cost")
    certs, ledger = certificates()
    exact(record["certificate_ledger"], ledger, "GPU certificate replay")
    # Fixed output budget prevents decompression of arbitrary-size input records.
    expected_bytes = sum(math.prod(x + 1 for x in spec.maxima) * 8 for spec in decoder_specs())
    with gzip.open(out / "device-outputs.bin.gz", "rb") as stream:
        raw = stream.read(expected_bytes + 1)
    require(len(raw) == expected_bytes, "GPU output data is missing, truncated or extended")
    expected_cases, offset, safe_names = [], 0, []
    for spec in decoder_specs():
        words = words_for(spec)
        width = len(words) * 4
        packed = decode_words(raw[offset:offset + width])
        lane = decode_words(raw[offset + width:offset + 2 * width])
        expected_packed, expected_lane = reference_outputs(spec, words)
        require(packed == expected_packed and lane == expected_lane, "GPU raw arithmetic output differs")
        safe = certs[spec.name]["decision"]["equivalent"]
        case = case_record(spec, words, packed, lane, safe, offset)
        require(safe == (case["unequal_words"] == 0), "GPU decision and complete replay differ")
        witness = certs[spec.name]["decision"]["least_counterexample"]
        require(case["least_counterexample_digits"] == (None if witness is None else witness["digits"]),
                "GPU least witness and exact certificate differ")
        expected_cases.append(case)
        if safe:
            safe_names.append(spec.name)
        offset += width * 2
    exact(record["cases"], expected_cases, "GPU case aggregates")
    timings = record["timings"]
    require(type(timings) is list and len(timings) == len(safe_names) * len(SIZES) * PAIRS,
            "Missing/extra paired GPU samples")
    expected_keys = {(name, size, pair) for name in safe_names for size in SIZES for pair in range(PAIRS)}
    observed = set()
    for row in timings:
        require(type(row) is dict and set(row) == {"name", "words", "pair", "order", "packed", "lane"}, "Invalid paired row")
        require(type(row["words"]) is int and type(row["pair"]) is int, "Non-integer GPU sample index")
        key = (row["name"], row["words"], row["pair"])
        require(key in expected_keys and key not in observed, "Duplicate or invalid GPU sample")
        observed.add(key)
        require(row["order"] == (["packed", "lane"] if row["pair"] % 2 == 0 else ["lane", "packed"]), "Wrong paired order")
        sample_valid(row["packed"])
        sample_valid(row["lane"])
    require(type(record["warmups"]) is list and len(record["warmups"]) == len(safe_names) * len(SIZES), "Missing warmups")
    observed_warmups = set()
    for row in record["warmups"]:
        require(type(row) is dict and set(row) == {"name", "words", "packed", "lane"}, "Invalid warmup")
        require(type(row["words"]) is int, "Non-integer warmup size")
        key = (row["name"], row["words"])
        require(key in {(n, s) for n in safe_names for s in SIZES} and key not in observed_warmups, "Duplicate/invalid warmup")
        observed_warmups.add(key)
        sample_valid(row["packed"])
        sample_valid(row["lane"])
    exact(record["summary"], summarize(timings), "GPU statistics")
    return {"boxes": len(expected_cases), "safe_boxes": len(safe_names),
            "complete_words": expected_bytes // 8, "raw_output_bytes": expected_bytes,
            **record["summary"]}


def run(out):
    from native.cuda_decoder_driver import DecoderDevice
    require(not out.exists(), "Use a new output directory; existing evidence is not overwritten")
    source_context = bindings()
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter_ns()
    certs, ledger = certificates()
    guard_ns = time.perf_counter_ns() - start
    raw, cases, timings, warmups = bytearray(), [], [], []
    device_start = time.perf_counter_ns()
    with DecoderDevice(ROOT / "native/decoder_gpu.ptx") as device:
        device_setup_ns = time.perf_counter_ns() - device_start
        environment = {"execution": "actual CUDA Driver API launches", "started_utc": started,
                       "system": platform.platform(), "machine": platform.machine(),
                       "python": platform.python_version(), "device": device.info, "cpu_model": cpu_model(),
                       "clock_control": "not locked", "host_affinity": "not pinned",
                       "exclusive_device": False, "display_scheduling": "host display GPU; WDDM on Windows"}
        try:
            output = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,compute_cap,memory.total",
                                     "--format=csv,noheader"], capture_output=True, text=True, timeout=10, check=True)
            environment["nvidia_smi"] = output.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            environment["nvidia_smi"] = None
        setup_costs = {"context_ns": device.context_ns, "module_load_ns": device.module_load_ns,
                      "certificate_check_ns": guard_ns, "device_setup_ns": device_setup_ns,
                      "cache_state": "driver caches not purged"}
        for spec in decoder_specs():
            words = words_for(spec)
            bias = sum(value << (8 * i) for i, value in enumerate(spec.biases))
            packed, _ = device.run(words, spec.scale, bias, "packed")
            lane, _ = device.run(words, spec.scale, bias, "lane")
            expected_packed, expected_lane = reference_outputs(spec, words)
            require(packed == expected_packed and lane == expected_lane, "GPU conformance failed")
            safe = certs[spec.name]["decision"]["equivalent"]
            case = case_record(spec, words, packed, lane, safe, len(raw))
            require(safe == (case["unequal_words"] == 0), "GPU admission decision failed")
            cases.append(case)
            raw.extend(encode_words(packed))
            raw.extend(encode_words(lane))
            if not safe:
                continue
            for size in SIZES:
                fixture = [words[i % len(words)] for i in range(size)]
                expected = [expected_lane[i % len(words)] for i in range(size)]
                warmup = {"name": spec.name, "words": size}
                for arm in ("packed", "lane"):
                    values, sample = device.run(fixture, spec.scale, bias, arm)
                    require(values == expected, "GPU warmup output differs")
                    sample_valid(sample)
                    warmup[arm] = sample
                warmups.append(warmup)
                for pair in range(PAIRS):
                    order = ["packed", "lane"] if pair % 2 == 0 else ["lane", "packed"]
                    row = {"name": spec.name, "words": size, "pair": pair, "order": order}
                    for arm in order:
                        values, sample = device.run(fixture, spec.scale, bias, arm)
                        require(values == expected, "Timed GPU output differs")
                        sample_valid(sample)
                        row[arm] = sample
                    timings.append(row)
    protocol = {"sizes": list(SIZES), "pairs_per_case": PAIRS, "block_threads": 128,
                "order": "packed-first on even pairs; lane-first on odd pairs",
                "event_interval": "one launch between default-stream events; includes scheduling and enqueue gaps",
                "transfer_call": "input copy, output poisoning, launch/event management, wait and complete guarded output copy",
                "excluded": "context/module setup, host fixture allocation, reference validation, log/statistic generation",
                "allocation_bytes": 2 * (65536 + 2) * 4,
                "timed_domain": "only certificate-admitted boxes; deterministic fixture cycling"}
    exact(bindings(), source_context, "Source context changed during GPU execution")
    record = {"format": "decoder-gpu-evidence", "environment": environment, "protocol": protocol,
              "source_bindings": source_context, "certificate_ledger": ledger, "cases": cases,
              "timings": timings, "warmups": warmups, "setup_costs": setup_costs, "summary": summarize(timings)}
    out.mkdir(parents=True)
    with gzip.GzipFile(filename=str(out / "device-outputs.bin.gz"), mode="wb", mtime=0) as stream:
        stream.write(raw)
    (out / "study.json").write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return check(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "check"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps((run if args.mode == "run" else check)(args.out), indent=2, allow_nan=False))
