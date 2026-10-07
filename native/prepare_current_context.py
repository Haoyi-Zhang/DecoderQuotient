#!/usr/bin/env python3
"""Copy only the three fixed measured TeX inputs into a fresh current context.

SPDX-License-Identifier: MIT. No historical code execution, network, compiler,
timing, source/result/receipt rebinding or overwrites. All inputs and destination
admission are checked before writes. A fresh, isolated destination is required;
this is not a concurrent-filesystem transaction or a full paper export/build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ARTIFACT = Path(__file__).resolve().parents[1]
INPUTS = {
    'native_cpu_macros.tex': (837, '25f1278c37a453cab7b2a6aaef474cf4e71426af01dbc16d7fc57e3d300ea51a'),
    'native_cpu_summary.tex': (375, '56c8738d92dd722d6ac1822d6018ff401f986943f0cd0047017d7bad0df37e8e'),
    'supplement_native_cases.tex': (5429, '2dcbc6b11f30936a483bc0f7d0aa8fc96cb333177587095dab6d9e6b37a83c0a'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_bytes(body, expected):
    size, digest = expected
    require(type(body) is bytes and type(size) is int and size >= 0 and
            isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) is not None,
            'invalid byte/digest declaration')
    require(len(body) == size and hashlib.sha256(body).hexdigest() == digest,
            'measured input byte identity mismatch')
    return body


def plain_path(path):
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(),
                'linked source/destination requires separate review')
    return path.resolve()


def read_input(source, expected):
    source = plain_path(source)
    require(source.is_file() and source.stat().st_size == expected[0], 'missing/wrong-size measured input')
    with source.open('rb') as stream:
        body = stream.read(expected[0]+1)
    return checked_bytes(body, expected)


def preflight(historical_project, paper_dir):
    historical = plain_path(historical_project)
    paper = plain_path(paper_dir)
    require(not paper.is_relative_to(historical), 'destination must not modify historical context')
    destinations = [(name, plain_path(paper/'generated'/name)) for name in INPUTS]
    for _, destination in destinations:
        require(not destination.exists(), 'destination input already exists: '+destination.name)
    # Snapshot all three verified byte strings before making even a directory.
    return [(destination, read_input(historical/'paper/generated'/name, INPUTS[name]))
            for name, destination in destinations]


def install_inputs(historical_project, paper_dir):
    prepared = preflight(historical_project, paper_dir)
    copied = []
    for destination, body in prepared:
        destination.parent.mkdir(parents=True, exist_ok=True)
        plain_path(destination)
        with destination.open('xb') as target:  # Exclusive creation; never overwrite.
            target.write(body)
        copied.append({'file': destination.name, 'bytes': len(body),
                       'sha256': hashlib.sha256(body).hexdigest()})
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-project', type=Path, required=True)
    parser.add_argument('--paper-dir', type=Path, default=ARTIFACT.parent/'paper')
    args = parser.parse_args()
    copied = install_inputs(args.historical_project, args.paper_dir)
    print(json.dumps({'copied_inputs': len(copied), 'files': copied,
                      'scope': 'Exact retained generated inputs only; no source/result rebinding or paper build.'}, sort_keys=True))


if __name__ == '__main__':
    main()
