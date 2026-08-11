from stockerr.discovery.consistency import compute_consistency

GOOD = dict(net_income=[100, 120, 140, 160], equity=[500, 520, 540, 560],
            revenue=[1000, 1100, 1250, 1400], fcf=[50, 60, 70, 80])
BAD = dict(net_income=[100, -20, 50, 10], equity=[500, 500, 500, 500],
           revenue=[1000, 900, 950, 800], fcf=[50, -10, -5, 20])


def test_consistency_good_beats_bad():
    g = compute_consistency(**GOOD)
    b = compute_consistency(**BAD)
    assert g.available and b.available
    assert g.score > b.score
    assert g.score >= 80          # steady ROE>15, rising rev/earnings, unbroken FCF


def test_consistency_unavailable_without_data():
    assert compute_consistency().available is False


def test_partial_inputs_renormalize():
    s = compute_consistency(fcf=[10, 20, 30])   # only the FCF streak is present
    assert s.available and s.score == 100.0
