"""Goc nhin toi gian ve Deployment target - du lieu chung cho Safety, Executor, Rule-based."""
from dataclasses import dataclass, field


@dataclass
class TargetView:
    deployment: str
    replicas: int                 # so replica mong muon (spec.replicas)
    ready: int                    # so pod Ready
    bad_pods: int                 # CrashLoop/OOMKilled/NotReady qua 60s
    min_replicas: int
    max_replicas: int
    resource_adjusts: int         # so lan RESOURCE_ADJUST trong su co hien tai
    revisions: int                # so ReplicaSet (revision) cua Deployment
    recent_rollout: bool          # image/env khac ban on dinh va moi trong 30 phut
    cpu_request_cores: float      # CPU request cua 1 pod
    cpu_free_cores: float         # CPU allocatable con trong cua cum
    incident_open: bool = False
    seconds_since_last_action: float = 1e9
    cooldowns: dict = field(default_factory=dict)   # {Action: so giay cooldown con lai}
