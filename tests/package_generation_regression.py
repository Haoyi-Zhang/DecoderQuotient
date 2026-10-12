"""Declared decoder display mapping and exact package-table mutation controls.

The retained records are read, never regenerated or timed. Temporary fixtures
exercise the same complete generated-input gate used by the package command.
This explicit CI command also works in the flat artifact-only checkout.
"""
from importlib.metadata import version
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ARTIFACT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ARTIFACT))
from bptc.publication_cases import decoder_specs
from tools.generate_paper import DECODER_PROFILE_LABELS,generate
from tools.package_check import check_generated_inputs

TABLE='\n'.join([
    r'\begin{tabular}{lrrrr}',r'\toprule',
    r'Profile & Cases & Equal & Unequal & Oracle inputs \\',r'\midrule',
    r'Full nibble domain & 10 & 5 & 5 & 0 \\',
    r'Small enumerated domain & 10 & 8 & 2 & 2560 \\',
    r'Alternating lanes & 10 & 5 & 5 & 2560 \\',
    r'\bottomrule',r'\end{tabular}',''])


class PackageGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated=generate(ARTIFACT)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paper=Path(self.temp.name)/'paper'
        (self.paper/'generated').mkdir(parents=True)
        for name,text in self.generated.items():
            (self.paper/'generated'/name).write_text(text,encoding='utf-8')

    def table(self,text):
        (self.paper/'generated/decoder_families.tex').write_text(text,encoding='utf-8')

    def rejects(self,text):
        self.table(text)
        with self.assertRaisesRegex(ValueError,'missing/stale generated TeX: decoder_families.tex'):
            check_generated_inputs(self.paper,ARTIFACT)

    def test_declared_mapping_has_the_actual_domain_meaning(self):
        self.assertEqual(DECODER_PROFILE_LABELS,{
            'full-nibble-box':'Full nibble domain',
            'tiny-oracle-box':'Small enumerated domain',
            'alternating-lanes':'Alternating lanes'})
        self.assertEqual({spec.provenance:tuple(spec.maxima) for spec in decoder_specs()},
                         {'full-nibble-box':(15,15,15,15),
                          'tiny-oracle-box':(3,3,3,3),
                          'alternating-lanes':(15,0,15,0)})

    def test_clean_display_names_and_all_current_numbers_pass(self):
        self.assertEqual(self.generated['decoder_families.tex'],TABLE)
        check_generated_inputs(self.paper,ARTIFACT)

    def test_all_twelve_numeric_cells_are_bound(self):
        lines=TABLE.splitlines(True)
        for row in range(4,7):
            for column in range(1,5):
                with self.subTest(row=row,column=column):
                    changed=lines.copy()
                    fields=changed[row].split(' & ')
                    old=re.match(r'\d+',fields[column]).group()
                    fields[column]=str(int(old)+1)+fields[column][len(old):]
                    changed[row]=' & '.join(fields)
                    self.rejects(''.join(changed))

    def test_equal_unequal_redistribution_preserving_total_is_rejected(self):
        self.rejects(TABLE.replace('10 & 5 & 5 & 0','10 & 6 & 4 & 0'))

    def test_all_display_labels_are_bound_not_arbitrary_aliases(self):
        for label in DECODER_PROFILE_LABELS.values():
            with self.subTest(label=label):self.rejects(TABLE.replace(label,'Other domain'))

    def test_provenance_identifiers_are_not_accepted_as_display_labels(self):
        for family,label in DECODER_PROFILE_LABELS.items():
            with self.subTest(family=family):self.rejects(TABLE.replace(label,family))

    def test_semantically_swapped_labels_are_rejected(self):
        self.rejects(TABLE.replace('Full nibble domain','TEMP').replace(
            'Small enumerated domain','Full nibble domain').replace('TEMP','Small enumerated domain'))

    def test_missing_duplicated_or_reordered_rows_are_rejected(self):
        lines=TABLE.splitlines(True)
        for altered in (lines[:4]+lines[5:],lines[:5]+[lines[4]]+lines[5:],
                        lines[:4]+[lines[5],lines[4],lines[6]]+lines[7:]):
            with self.subTest(table=altered):self.rejects(''.join(altered))

    def test_unknown_or_missing_declared_profile_is_not_a_fallback(self):
        for mapping in ({'unlisted-profile':'Other domain'},{}):
            with self.subTest(mapping=mapping),patch.dict(DECODER_PROFILE_LABELS,mapping,clear=True):
                with self.assertRaisesRegex(ValueError,'profile/display mapping'):
                    generate(ARTIFACT)

    def test_other_generated_inputs_remain_exactly_checked(self):
        for name,text in self.generated.items():
            if name=='decoder_families.tex':continue
            with self.subTest(name=name):
                target=self.paper/'generated'/name
                target.write_text(text+'% mutation\n',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'missing/stale generated TeX: '+re.escape(name)):
                    check_generated_inputs(self.paper,ARTIFACT)
                target.write_text(text,encoding='utf-8')

    def test_reportlab_is_declared_installed_and_in_the_actual_ci_path(self):
        requirements=(ARTIFACT/'requirements-package.txt').read_text()
        self.assertIn('reportlab==4.4.9',requirements.splitlines())
        self.assertEqual(version('reportlab'),'4.4.9')
        workflow=(ARTIFACT/'.github/workflows/scientific-checks.yml').read_text()
        finite=workflow.split('  finite-semantics:\n',1)[1].split('  retained-current-correctness:\n',1)[0]
        self.assertLess(finite.index('pip install -r requirements-package.txt'),
                        finite.index('tests/package_generation_regression.py'))
        self.assertNotIn('continue-on-error:',finite)


if __name__=='__main__':
    unittest.main(verbosity=2)
