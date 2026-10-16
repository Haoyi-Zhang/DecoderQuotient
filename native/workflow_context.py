"""Preserve measured source identity separately from current semantic replay."""
import hashlib
import json
from pathlib import Path

def measured_sources(root, declarations, expected_paths):
    root = Path(root)
    if set(declarations) != set(expected_paths):
        raise ValueError('workflow measured source set differs')
    frozen = root/'data/workflow_measured_sources.json'
    archive = json.loads(frozen.read_text(encoding='utf-8')) if frozen.is_file() else {}
    bindings = {}
    for rel, digest in declarations.items():
        current = hashlib.sha256((root/rel).read_bytes()).hexdigest()
        if current != digest:
            source = archive.get(rel)
            if type(source) is not str or hashlib.sha256(source.encode('utf-8')).hexdigest() != digest:
                raise ValueError('workflow measured source unavailable or changed: '+rel)
        bindings[rel] = {'measured': digest, 'current': current}
    return {'bindings': bindings,
            'measured_sources_are_current': all(v['measured']==v['current'] for v in bindings.values()),
            'scope': 'Original source bytes bind retained timing; current code independently replays the saved packets. No current-source timing is inferred.'}
