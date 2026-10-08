from loans.eligibility import is_eligible


def test_good_applicant_is_eligible():
    assert is_eligible(720, 100_000, 10_000)


def test_low_score_is_not_eligible():
    assert not is_eligible(500, 100_000, 10_000)
