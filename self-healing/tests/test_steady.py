from selfheal.chaos.steady import steady_ok, wait_steady

CALM = {"p99_ms": 30.0, "err": 0.0, "incident": 0.0, "anomaly": 0.4, "unavailable": 0.0}


def test_calm_cluster_is_steady():
    ok, why = steady_ok(CALM, 305, 0.01, 0.7)
    assert ok and not why


def test_each_condition_blocks_injection():
    cases = [{"p99_ms": 3615.0},           
             {"p99_ms": None},              
             {"err": 0.05},
             {"incident": 1.0},             
             {"anomaly": 0.75},            
             {"unavailable": 1.0}]
    for change in cases:
        ok, why = steady_ok({**CALM, **change}, 305, 0.01, 0.7)
        assert not ok and why, change


def test_missing_optional_series_do_not_block():
   
    ok, _ = steady_ok({**CALM, "incident": None, "err": None}, 305, 0.01, 0.7)
    assert ok


def _run(seq, need=4, timeout=600.0):
    reads, clock = iter(seq), [0.0]
    def sleep(s):
        clock[0] += s
    return wait_steady(lambda: next(reads), 305, 0.01, 0.7, need=need, step=15, timeout=timeout,
                       sleep=sleep, now=lambda: clock[0], log=lambda *_: None)


def test_streak_resets_on_noise_then_waits_for_four_calm_reads():
    noisy = {**CALM, "p99_ms": 900.0}
    assert _run([CALM, CALM, noisy, CALM, CALM, CALM, CALM])


def test_gives_up_after_timeout():
    noisy = {**CALM, "incident": 1.0}
    assert not _run([noisy] * 100, timeout=60)
