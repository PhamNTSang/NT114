"""Ham thuong da thanh phan (de cuong 4.2.4) va bo dem chi so cua 1 episode."""
from dataclasses import dataclass

from .spaces import Action


@dataclass(frozen=True)
class RewardWeights:
    alpha: float = 0.4     # SLA
    beta: float = 0.3      # MTTR
    gamma: float = 0.2     # chi phi
    delta: float = 0.1     # an toan
    lam: float = 0.5       # he so phat moi replica them
    penalty: float = 10.0  # P


def sla_ok(p99_ms: float, err_rate: float, slo_p99_ms: float, slo_err: float) -> bool:
    return p99_ms <= slo_p99_ms and err_rate <= slo_err


def compute_reward(*, sla: bool, recovered_now: bool, t_recover_s: float, extra_replicas: int,
                   unsafe: bool, t_max_s: float, w: RewardWeights = RewardWeights()) -> float:
    # Chi phat khi vi pham SLA (0/-1), KHONG thuong +1: episode ket thuc khi phuc hoi, neu moi buoc dat SLA
    # duoc +alpha thi agent co loi khi keo dai su co (reward hacking, phat hien 22/11 o ppo_test2).
    r_sla = 0.0 if sla else -1.0
    r_mttr = (t_max_s - t_recover_s) / t_max_s if recovered_now else 0.0
    r_cost = -w.lam * max(0, extra_replicas)
    r_safety = -w.penalty if unsafe else 0.0
    return w.alpha * r_sla + w.beta * r_mttr + w.gamma * r_cost + w.delta * r_safety


@dataclass
class EpisodeTracker:
    step_sec: int
    t_max_s: int
    hold_steps: int
    base_replicas: int
    steps: int = 0
    streak: int = 0
    streak_start: int = 0
    recovered: bool = False
    t_recover_s: float | None = None
    relapses: int = 0
    sla_steps: int = 0
    replica_seconds: float = 0.0
    n_actions: int = 0
    n_proposed: int = 0
    n_blocked: int = 0
    cascade: bool = False
    _paid: bool = False

    def update(self, *, sla: bool, healthy: bool, replicas: int, proposed: int, executed: int) -> bool:
        """Cap nhat sau 1 buoc. Tra ve True neu buoc nay la lan dau dat phuc hoi (tra r_MTTR)."""
        self.steps += 1
        self.sla_steps += int(sla)
        self.replica_seconds += replicas * self.step_sec
        if proposed != Action.NO_OP:
            self.n_proposed += 1
            if executed == Action.NO_OP:
                self.n_blocked += 1
            else:
                self.n_actions += 1
        if healthy:
            if self.streak == 0:
                self.streak_start = self.steps - 1
            self.streak += 1
            if not self.recovered and self.streak >= self.hold_steps:
                self.recovered = True
                self.t_recover_s = self.streak_start * self.step_sec
                first, self._paid = not self._paid, True
                return first
        else:
            self.streak = 0
            if self.recovered:          # tai phat (vd trong kich ban tai dot bien)
                self.recovered = False
                self.relapses += 1
        return False

    @property
    def truncated(self) -> bool:
        return self.steps * self.step_sec >= self.t_max_s

    def metrics(self) -> dict:
        return {
            "recovered": self.recovered,
            "mttr_s": self.t_recover_s if self.recovered else float(self.t_max_s),
            "scr": self.sla_steps / max(self.steps, 1),
            "rc_replica_s": self.replica_seconds,
            "ae": self.n_actions,
            "svr": self.n_blocked / max(self.n_proposed, 1),
            "relapses": self.relapses,
            "steps": self.steps,
            "cascade": self.cascade,
        }
