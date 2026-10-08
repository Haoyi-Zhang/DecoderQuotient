"""Materialize the recorded measurement's source context without a private repository.

The five-file fixture contains two measured Python kernels and three generated
TeX inputs. Timings and the remaining measured sources are copied unchanged.
Only a fresh destination outside the current artifact is accepted.
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ARTIFACT = Path(__file__).resolve().parents[1]
KERNELS = ('bptc/accumulator_checker.py', 'bptc/exact_accumulator.py')
TEX_INPUTS = {
    'native_cpu_macros.tex': (837, '25f1278c37a453cab7b2a6aaef474cf4e71426af01dbc16d7fc57e3d300ea51a'),
    'native_cpu_summary.tex': (375, '56c8738d92dd722d6ac1822d6018ff401f986943f0cd0047017d7bad0df37e8e'),
    'supplement_native_cases.tex': (5429, '2dcbc6b11f30936a483bc0f7d0aa8fc96cb333177587095dab6d9e6b37a83c0a'),
}


def measured_fixture(artifact: Path = ARTIFACT) -> dict[str, bytes]:
    """Read and validate the exact measured fixture without extracting it."""
    provenance = json.loads((artifact/'results/native-cpu/provenance.json').read_text(encoding='utf-8'))
    expected = {'artifact/'+p for p in KERNELS} | {'paper/generated/'+p for p in TEX_INPUTS}
    with zipfile.ZipFile(artifact/'data/measured_context.zip') as archive:
        if len(archive.infolist()) != 5 or set(archive.namelist()) != expected:
            raise ValueError('Measured fixture membership differs')
        prepared = {name: archive.read(name) for name in sorted(expected)}
    for kernel in KERNELS:
        if hashlib.sha256(prepared['artifact/'+kernel]).hexdigest() != provenance['scientific_sources'][kernel]:
            raise ValueError('Measured kernel differs: '+kernel)
    for name, (size, digest) in TEX_INPUTS.items():
        body = prepared['paper/generated/'+name]
        if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
            raise ValueError('Measured generated input differs: '+name)
    return prepared


def materialize(destination: Path) -> Path:
    destination = destination.absolute()
    for part in (destination, *destination.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Use an unlinked destination')
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(ARTIFACT.parent):
        raise ValueError('Use a fresh destination outside the current project')
    prepared = measured_fixture()
    provenance = json.loads((ARTIFACT/'results/native-cpu/provenance.json').read_text(encoding='utf-8'))
    shutil.copytree(ARTIFACT, destination/'artifact',
                    ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', '.pytest_cache'))
    for name, body in prepared.items():
        path = destination/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    for name, digest in provenance['scientific_sources'].items():
        if hashlib.sha256((destination/'artifact'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Measured source context differs: '+name)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.out))


if __name__ == '__main__':
    main()
