from ..config import SETTINGS
from ..spaces import Action


class RuleBasedPolicy:
    name = "rule"

    def __init__(self, settings=SETTINGS):
        self.s = settings

    def act(self, obs, raw: dict, view, mask) -> int:
        A, s = Action, self.s

        def ok(a):
            return bool(mask[a])

        slo_bad = raw.get("lat_p99", 0.0) > s.slo_p99_ms or raw.get("err_rate", 0.0) > s.slo_err
        # 1. Loi xuat hien sau khi trien khai phien ban moi -> ROLLBACK
        if view.recent_rollout and slo_bad and ok(A.ROLLBACK):
            return A.ROLLBACK
        # 2. Pod loi: giu dich vu song truoc roi moi restart
        if view.bad_pods > 0:
            if view.ready <= 1 and ok(A.SCALE_UP):
                return A.SCALE_UP
            if ok(A.RESTART_POD):
                return A.RESTART_POD
        # 3. Memory sap cham limit / OOMKilled
        if raw.get("tgt_mem", 0.0) > 0.85 and ok(A.RESOURCE_ADJUST):
            return A.RESOURCE_ADJUST
        # 4. Qua tai CPU, vi pham SLO hoac du bao qua tai
        if (raw.get("tgt_cpu", 0.0) > 0.8 or slo_bad or raw.get("pred_cpu", 0.0) > 0.8) and ok(A.SCALE_UP):
            return A.SCALE_UP
        # 5. Bat thuong khong ro nguyen nhan -> co lap pod nghi van
        if raw.get("anomaly", 0.0) > 0.7 and ok(A.TRAFFIC_SHIFT):
            return A.TRAFFIC_SHIFT
        # 6. Du thua tai nguyen khi khong con su co
        if not view.incident_open and raw.get("tgt_cpu", 1.0) < 0.3 and ok(A.SCALE_DOWN):
            return A.SCALE_DOWN
        return A.NO_OP