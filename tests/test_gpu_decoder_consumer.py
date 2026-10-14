"""Portable strict-consumer and literal arithmetic checks; no GPU execution."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from bptc.packed_decoder import DecoderSpec
from native import gpu_decoder_study as study
from native.cuda_decoder_driver import DecoderDevice


class GpuDecoderConsumerTests(unittest.TestCase):
    def test_literal_cross_byte_carry_and_top_word_wrap(self):
        spec = DecoderSpec("literal", 255, (15, 15, 15, 15), (0, 0, 0, 0))
        packed, lane = study.reference_outputs(spec, [0, 15, 0x0F000000])
        self.assertEqual(packed, [0, 3825, 0xF1000000])
        self.assertEqual(lane, [0, 241, 0xF1000000])
        # The top carry is unobserved; carry from a lower lane is observable.
        self.assertEqual(study.case_record(spec, [0, 15, 0x0F000000], packed, lane, False, 0)[
            "least_counterexample_digits"], [15, 0, 0, 0])

    def test_byte_correction_wraps_without_cross_lane_carry(self):
        spec = DecoderSpec("literal", 1, (15, 15, 15, 15), (255, 254, 253, 252))
        packed, lane = study.reference_outputs(spec, [0x04030201])
        self.assertEqual(packed, [0])
        self.assertEqual(lane, [0])

    def test_little_endian_output_roundtrip(self):
        values = [0, 0x01234567, 0xFFFFFFFF]
        self.assertEqual(study.encode_words(values), b"\x00\x00\x00\x00\x67\x45\x23\x01\xff\xff\xff\xff")
        self.assertEqual(study.decode_words(study.encode_words(values)), values)
        with self.assertRaises(ValueError):
            study.decode_words(b"\x00")

    def test_event_and_host_intervals_reject_invalid_types(self):
        for record in ({"event_ms": True, "transfer_call_ns": 1},
                       {"event_ms": float("nan"), "transfer_call_ns": 1},
                       {"event_ms": 1.0, "transfer_call_ns": True},
                       {"event_ms": 0.0, "transfer_call_ns": 1},
                       {"event_ms": 1.0, "transfer_call_ns": 0},
                       {"event_ms": 1.0, "transfer_call_ns": 1, "extra": 0}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                study.sample_valid(record)

    def test_driver_admission_before_any_device_call(self):
        device = DecoderDevice.__new__(DecoderDevice)
        device.functions = {"packed": None, "lane": None}
        for words, scale, bias, arm in (([], 1, 0, "packed"), ([True], 1, 0, "packed"),
                ([-1], 1, 0, "packed"), ([1 << 32], 1, 0, "packed"),
                ([0] * 65537, 1, 0, "packed"), ([0], True, 0, "packed"),
                ([0], 256, 0, "packed"), ([0], 1, True, "packed"),
                ([0], 1, 1 << 32, "packed"), ([0], 1, 0, "missing")):
            with self.subTest(words=words[:1], scale=scale, bias=bias, arm=arm), self.assertRaises(ValueError):
                device.run(words, scale, bias, arm)
        import ctypes
        device.ctx = ctypes.c_void_p()
        with self.assertRaises(RuntimeError):
            device.run([0], 1, 0, "packed")

    def test_metadata_read_rejects_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "study.json").write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "fixed record bound"):
                study.check(out)

    @classmethod
    def setUpClass(cls):
        cls.retained = study.ROOT / "results/gpu-decoder"
        cls.record = json.loads((cls.retained / "study.json").read_text(encoding="utf-8"))
        cls.binary = (cls.retained / "device-outputs.bin.gz").read_bytes()

    def test_complete_retained_device_words(self):
        result = study.check(self.retained)
        self.assertEqual((result["boxes"], result["safe_boxes"], result["complete_words"], result["pairs"]),
                         (30, 18, 660480, 540))

    def test_reject_record_controls(self):
        for kind in ("binding", "case-type", "missing-pair", "duplicate-pair", "timing-type",
                     "nonfinite", "wrong-order", "missing-warmup", "aggregate", "raw-word", "raw-truncated"):
            record = deepcopy(self.record)
            binary = self.binary
            if kind == "binding": record["source_bindings"]["native/decoder_gpu.ptx"] = "0" * 64
            elif kind == "case-type": record["cases"][0]["admitted_equivalent"] = 1
            elif kind == "missing-pair": record["timings"].pop()
            elif kind == "duplicate-pair": record["timings"][1] = deepcopy(record["timings"][0])
            elif kind == "timing-type": record["timings"][0]["packed"]["transfer_call_ns"] = True
            elif kind == "nonfinite": record["timings"][0]["packed"]["event_ms"] = float("nan")
            elif kind == "wrong-order": record["timings"][0]["order"].reverse()
            elif kind == "missing-warmup": record["warmups"].pop()
            elif kind == "aggregate": record["summary"]["pairs"] -= 1
            elif kind in ("raw-word", "raw-truncated"):
                raw = bytearray(gzip.decompress(binary))
                if kind == "raw-word": raw[0] ^= 1
                else: raw.pop()
                binary = gzip.compress(raw, mtime=0)
            with tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                (out / "study.json").write_text(json.dumps(record), encoding="utf-8")
                (out / "device-outputs.bin.gz").write_bytes(binary)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    study.check(out)


if __name__ == "__main__":
    unittest.main()
