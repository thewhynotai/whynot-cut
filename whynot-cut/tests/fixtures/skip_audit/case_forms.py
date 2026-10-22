# Fixture for test_skip_audit.py: one of every skip form, each with a condition the audit cannot class (unknown).
# Never run (not named test_*.py); only parsed.
import unittest
from unittest import SkipTest

import pytest

requires_thing = unittest.skipUnless(THING_READY, "the thing is not ready")


@unittest.skip("form: skip")
class A(unittest.TestCase):
    @unittest.skipIf(FLAG, "form: skipIf")
    def test_a(self):
        pass

    @unittest.skipUnless(FLAG, "form: skipUnless")
    def test_b(self):
        pass

    @unittest.expectedFailure
    def test_c(self):
        pass

    def test_d(self):
        self.skipTest("form: skipTest")

    def test_e(self):
        raise unittest.SkipTest("form: raise unittest.SkipTest")

    def test_f(self):
        raise SkipTest("form: raise SkipTest")

    def test_g(self):
        raise SkipTest

    @requires_thing
    def test_h(self):
        pass

    @pytest.mark.skip(reason="form: pytest skip")
    def test_i(self):
        pass

    @pytest.mark.skipif(FLAG, reason="form: pytest skipif")
    def test_j(self):
        pass

    @pytest.mark.xfail(reason="form: pytest xfail")
    def test_k(self):
        pass
