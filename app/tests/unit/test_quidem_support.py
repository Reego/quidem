import pytest

import math

from ...quidem import UserVisibility, VotingAlgorithm

class TestUserVisibility:

    def test(self):
        assert UserVisibility.visible_to_all is not None
        assert UserVisibility.visible_to_author is not None
        assert UserVisibility.anonymous is not None

class TestVotingAlgorithm:

    # returns whether
    def algorithm_test(self, attr, method, input, output, approx=False):
        algorithm = VotingAlgorithm.get_algorithm(attr)
        in_out_equivalence = math.isclose(algorithm(input), output, abs_tol=1e-5) if approx else algorithm(input) == output
        assert algorithm is method
        return algorithm is method and in_out_equivalence

    def test_linear(self):
        assert self.algorithm_test(VotingAlgorithm.linear, VotingAlgorithm.flinear, 9, 9)

    def test_square(self):
        assert self.algorithm_test(VotingAlgorithm.square, VotingAlgorithm.fsquare, -4, 16)

    def test_cube(self):
        assert self.algorithm_test(VotingAlgorithm.cube, VotingAlgorithm.fcube, -5, -125)

    def test_exponential(self):
        assert self.algorithm_test(VotingAlgorithm.exponential, VotingAlgorithm.fexponential, 3, 20.0855369, True)

    def test_logarithmic(self):
        assert self.algorithm_test(VotingAlgorithm.logarithmic, VotingAlgorithm.flogarithmic, 5, 1.6094379, True)
