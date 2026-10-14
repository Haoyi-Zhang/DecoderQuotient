"""Derive manuscript inputs from complete retained GPU outputs and raw pairs."""
import argparse
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native.gpu_decoder_study import check, require


def derived(out):
    result = check(out)
    values = {
        "GpuDecoderWords": f"{result['complete_words']:,}",
        "GpuDecoderPairs": str(result["pairs"]),
        "GpuDecoderSafe": str(result["safe_boxes"]),
        "GpuDecoderUnsafe": str(result["boxes"] - result["safe_boxes"]),
        "GpuDecoderEventMedian": f"{result['event_case_ratio_median']:.3f}",
        "GpuDecoderTransferMedian": f"{result['transfer_call_case_ratio_median']:.3f}",
    }
    macros = "".join("\\newcommand{\\" + key + "}{" + value + "}\n" for key, value in values.items())
    table = ["\\begin{tabular}{rcc}\n\\toprule\nWords & Event ratio & Transfer/call ratio \\\\\n\\midrule\n"]
    for size in (4096, 65536):
        rows = [row for row in result["per_case"] if row["words"] == size]
        cells = []
        for field in ("event_lane_over_packed", "transfer_call_lane_over_packed"):
            ratios = [row[field] for row in rows]
            cells.append(f"{statistics.median(ratios):.3f} [{min(ratios):.3f}, {max(ratios):.3f}]")
        table.append(f"{size:,} & {cells[0]} & {cells[1]} \\\\\n")
    table.append("\\bottomrule\n\\end{tabular}\n")
    return {"gpu_decoder_macros.tex": macros, "gpu_decoder_summary.tex": "".join(table)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--paper-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, content in derived(args.results_dir).items():
        path = args.paper_dir / "generated" / name
        if args.check:
            require(path.is_file() and path.read_text(encoding="utf-8") == content, "Missing or stale GPU manuscript input: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    print("GPU manuscript inputs match retained outputs and all raw pairs")
