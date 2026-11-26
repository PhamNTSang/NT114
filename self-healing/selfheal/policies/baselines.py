import math

from ..spaces import Action


class HPAEmulator:
    """desired = ceil(replicas * cpu / target); tolerance 10%; scale-down sau 300 s on dinh.
       Moi buoc env chi them/bot 1 replica -> HPA gia lap cham hon HPA that mot chut"""
    name = "hpa"

    def __init__(self, target: float = 0.7, tolerance: float = 0.1, stabilization_s: int = 300,
                 step_sec: int = 15, rps_per_pod: float | None = None):
        self.target, self.tol = target, tolerance
        self.stab_steps = stabilization_s // step_sec
        self.rps_per_pod = rps_per_pod
        self.low_steps = 0

    def reset(self) -> None:
        self.low_steps = 0

    def desired(self, raw: dict, replicas: int) -> int:
        cpu = raw.get("tgt_cpu", 0.0)
        want = replicas
        if abs(cpu / self.target - 1.0) > self.tol:
            want = math.ceil(replicas * cpu / self.target)
        if self.rps_per_pod:
            want = max(want, math.ceil(raw.get("rps", 0.0) / self.rps_per_pod))
        return max(1, want)

    def act(self, obs, raw, view, mask) -> int:
        n = max(view.replicas, 1)
        want = self.desired(raw, n)
        if want > n and mask[Action.SCALE_UP]:
            self.low_steps = 0
            return Action.SCALE_UP
        self.low_steps = self.low_steps + 1 if want < n else 0
        if self.low_steps >= self.stab_steps and mask[Action.SCALE_DOWN]:
            self.low_steps = 0
            return Action.SCALE_DOWN
        return Action.NO_OP


class KEDAEmulator(HPAEmulator):
    name = "keda"

    def __init__(self, **kw):
        super().__init__(rps_per_pod=100.0, **kw)