"""Retained timing sources must bind exact source bytes, never edited provenance."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from native.workflow_context import measured_sources

class WorkflowContextTests(unittest.TestCase):
    def test_current_and_measured_contexts_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'data').mkdir()
            (root/'source.py').write_bytes(b'original\n')
            digest = hashlib.sha256(b'original\n').hexdigest()
            declarations = {'source.py':digest}
            self.assertTrue(measured_sources(root,declarations,('source.py',))['measured_sources_are_current'])
            (root/'source.py').write_bytes(b'current\n')
            with self.assertRaisesRegex(ValueError,'unavailable or changed'):
                measured_sources(root,declarations,('source.py',))
            fixture = root/'data/workflow_measured_sources.json'
            fixture.write_text(json.dumps({'source.py':'original\n'}))
            self.assertFalse(measured_sources(root,declarations,('source.py',))['measured_sources_are_current'])
            fixture.write_text(json.dumps({'source.py':'wrong\n'}))
            with self.assertRaisesRegex(ValueError,'unavailable or changed'):
                measured_sources(root,declarations,('source.py',))

    def test_incomplete_source_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError,'source set'):
            measured_sources(Path(d),{},('missing.py',))

if __name__=='__main__': unittest.main()
