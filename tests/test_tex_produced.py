"""Test for single-file submission compiled from TeX source (TeX Produced)"""

from unittest import TestCase
import re
from datetime import datetime
# from filemanager.domain import Upload

import os.path
import shutil
import tempfile
import filecmp

from filemanager.arxiv.TeXProduced import check_tex_produced_pdf, check_tex_produced_ps

TEST_FILES_DIRECTORY = os.path.join(os.getcwd(), 'tests/test_files_tex_produced')

print(f"TEST DIR:{TEST_FILES_DIRECTORY}")

pdf_tests = []
pdf_tests.append(['file_does_not_exist', False, '', "File doesn't exist."])

# From Legacy
pdf_tests.append(['astro-ph-0610480.ethanneil.20289.pdf', True,
                  b'Creator:        dvips', 'PDF generated by dvips.'])
pdf_tests.append(['astro-ph-0703077.jf_sauvage.10062.pdf', True,
                  b'Creator:        dvips', 'PDF generated by dvips.'])
pdf_tests.append(['astro-ph.arimoto.4168.pdf', True,
                  b'Creator:         TeX', 'PDF produced by TeX.'])
pdf_tests.append(['astro-ph.ewhelan.18488.pdf', True, b'Creator:        TeX',
                  'PDF produced by pdfeTeX.'])
pdf_tests.append(['notex_compositionality.pdf', False, '',
                  'PDF not produced by TeX.'])
pdf_tests.append(['0706.4412.pdf', True, b'GOFKVE+CMR', 'TeX produced'])
pdf_tests.append(['0706.4328.pdf', True, b'WTBOIB+CMR', 'TeX produced'])
pdf_tests.append(['0706.3971.pdf', False, '', 'Not TeX produced.'])
pdf_tests.append(['0706.3927.pdf', True, b'COUOFV+CMR', 'TeX produced'])
pdf_tests.append(['0706.3906.pdf', True, b'AGKNIF+CMR', 'TeX produced'])
pdf_tests.append(['0706.3810.pdf', False, '', 'TeX produced'])
pdf_tests.append(['0611002.pdf', True, b'MWHYSM+CMR', ''])

pdf_tests.append(['GalluzziBalkancom2018.pdf', True, b'Creator:        TeX',
                  ''])

pdf_tests.append(['2738685LaTeX.pdf', True, b'Creator:        LaTeX',
                  'PDF generated by LaTeX '])
pdf_tests.append(['2745765withCairoFonts.pdf', True, b'CairoFont-1-0',
                  'Cairo Fonts - TeX produced'])
pdf_tests.append(['2748220withCairoCreator.pdf', True, '',
                  'Cairo Software - TeX produced'])

# False negative and false positive
# Supposed to be True
## pdf_tests.append(['0609584.pdf', True, '', 'No visible TeXisms or fonts.'])
# Incorrectly detected as TeX produced
##pdf_tests.append(['paperfinal.PDF', False, '', 'Not Tex-produced'])

pdf_tests.append(['sparsemult6.pdf', False, '',
                  'TeXmacs is not TeX Produced.'])
pdf_tests.append(['math0607661.tudateru.25992.tsuda_takenawa.pdf', True,
                  b'Producer:       dvipdfmx', 'dvipdfmx'])


pdf_tests.append(['0706.3906.pdf', True, '',
                  'TeX-produced. Detected TeX fonts.'])

#pdf_tests.append(['', '', '', ''])

ps_tests = []
ps_tests.append(['file_does_not_exist', False, '', "File doesn't exist."])
ps_tests.append(['astro-ph.fdarcang.22633.ps', True,
                 b'%%Creator: dvips(k) 5.95a Copyright 2005 Radical Eye Software\n',
                 'Expected "%%Creator: dvips(k) 5.95a Copyright 2005 Radical Eye Software"'])
ps_tests.append(['hep-th-0701130.pmho.24929.ps', True,
                 b'%%Creator: dvips(k) 5.95b Copyright 2005 Radical Eye Software\n',
                 'Expected "%%Creator: dvips(k) 5.95b Copyright 2005 Radical Eye Software"'])
ps_tests.append(['math.kristaly.24457.ps', True,
                 b'%%Creator: dvips(k) 5.86 Copyright 1999 Radical Eye Software\n',
                 'Expected "%%Creator: dvips(k) 5.86 Copyright 1999 Radical Eye Software"'])
ps_tests.append(['math.suri.13734.ps', True,
                 b'%%Creator: dvips(k) 5.95a Copyright 2005 Radical Eye Software\n',
                 'Expected "%%Creator: dvips(k) 5.95a Copyright 2005 Radical Eye Software"'])
ps_tests.append(['physics-0611280.pdomokos.2059.eps', True,
                 b'%%Creator: dvips(k) 5.92b Copyright 2002 Radical Eye Software\n',
                 'Expected "%%Creator: dvips(k) 5.92b Copyright 2002 Radical Eye Software"'])
ps_tests.append(['notex_kkpants.eps', False, '', 'Not TeX produced. Expected False.'])
ps_tests.append(['notex_orddps5.eps', False, '', 'Not TeX produced. Expected False.'])
ps_tests.append(['0190238.ps', True, b'%RBIBeginFontSubset: PSLGAP+CMR10\n',
                 'Detected TeX font(s): "%RBIBeginFontSubset: PSLGAP+CMR10". '
                 'Exported from PDF to allude our check.'])
ps_tests.append(['simple_tex_produced.ps', True,
                 b'%%Creator: dvips(k) 5.96.1 Copyright 2007 Radical Eye '
                 b'Software\n',
                 'Expected "%%Creator: dvips(k) 5.96.1 Copyright 2007 Radical '
                 'Eye Software"'])

# False negative
#ps_tests.append(['submit_0169105.ps', True, '',
#                 'Expected to detect this as tex-produced'])

class TestTeXProduced(TestCase):
    """Test for TeX Produced PDF/PS"""

    def test_tex_produced_pdf(self) -> None:
        """Test for TeX Produced PDF"""

        for test in pdf_tests:
            filename, expected, match, description = test

            # Eventually comment this out for quieter tests
            print(f"\n***Testing file '{filename}' for '{description}'\n")

            testfilename = os.path.join(TEST_FILES_DIRECTORY, filename)

            result = check_tex_produced_pdf(testfilename)

            if expected and match:
                self.assertEqual(result, match, description)
            elif expected:
                self.assertTrue(result, description)
            else:
                self.assertFalse(result, description)

    def test_tex_produced_ps(self) -> None:
        """Test for TeX Produced Postscript"""

        for test in ps_tests:
            filename, expected, match, description = test

            # Eventually comment this out for quieter tests
            print(f"\n***Testing file '{filename}' for '{description}'\n")

            testfilename = os.path.join(TEST_FILES_DIRECTORY, filename)

            result = check_tex_produced_ps(testfilename)

            if expected and match:
                self.assertEqual(result, match, description)
            elif expected:
                self.assertTrue(result, description)
            else:
                self.assertFalse(result, description)