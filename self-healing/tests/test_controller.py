from selfheal.controller import adjusts_after_open

BASE = {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "200m", "memory": "128Mi"}}
UP1 = {"requests": {"cpu": "120m", "memory": "77Mi"}, "limits": {"cpu": "240m", "memory": "154Mi"}}


def test_counter_kept_while_resources_still_adjusted():
    # su co moi tren deployment da bi chinh -> khong duoc dat lai ve 0 (tranh phinh tai nguyen vo han)
    assert adjusts_after_open(2, UP1, BASE) == 2


def test_counter_reset_when_back_to_baseline():
    assert adjusts_after_open(2, BASE, BASE) == 0


def test_unknown_baseline_keeps_counter():
    assert adjusts_after_open(1, UP1, None) == 1


def test_slo_debounce_needs_two_consecutive_violations():
    from selfheal.controller import slo_debounce
    streak, opened = slo_debounce(0, True, confirm=2)
    assert (streak, opened) == (1, False)          # lan 1: chua mo
    streak, opened = slo_debounce(streak, True, confirm=2)
    assert opened and streak == 0                  # lan 2 lien tiep: mo su co
    streak, _ = slo_debounce(1, False, confirm=2)
    assert streak == 0                             # dut quang -> dem lai tu dau
