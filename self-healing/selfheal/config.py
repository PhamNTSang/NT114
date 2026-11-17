"""Cau hinh chung, doc tu bien moi truong (ConfigMap selfheal-config khi chay trong cum)."""
import os
from dataclasses import dataclass

SERVICES = ["frontend", "cartservice", "checkoutservice", "currencyservice", "emailservice",
            "paymentservice", "productcatalogservice", "recommendationservice",
            "shippingservice", "adservice"]


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    namespace: str = _get("APP_NAMESPACE", "online-boutique")
    prometheus_url: str = _get(
        "PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
    step_sec: int = int(_get("STEP_SEC", "15"))
    t_max_sec: int = int(_get("T_MAX_SEC", "300"))
    healthy_hold_sec: int = int(_get("HEALTHY_HOLD_SEC", "60"))
    cooldown_sec: int = int(_get("COOLDOWN_SEC", "60"))
    slo_p99_ms: float = float(_get("SLO_P99_MS", "200"))
    slo_err: float = float(_get("SLO_ERR", "0.01"))
    min_replicas: int = int(_get("MIN_REPLICAS", "1"))
    max_replicas: int = int(_get("MAX_REPLICAS", "5"))
    max_resource_adjusts: int = int(_get("MAX_RESOURCE_ADJUSTS", "2"))
    anomaly_threshold: float = float(_get("ANOMALY_THRESHOLD", "0.7"))
    llm_backend: str = _get("LLM_BACKEND", "groq")            # groq | claude | ollama | off
    llm_model: str = _get("LLM_MODEL", "openai/gpt-oss-120b")
    llm_fallback_model: str = _get("LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")
    llm_conf_threshold: float = float(_get("LLM_CONF_THRESHOLD", "0.6"))
    slack_webhook: str = _get("SLACK_WEBHOOK_URL", "")
    dry_run: bool = _get("DRY_RUN", "false").lower() == "true"
    require_approval: str = _get("REQUIRE_APPROVAL", "")       # vd "ROLLBACK"

    @property
    def hold_steps(self) -> int:
        return self.healthy_hold_sec // self.step_sec

    @property
    def max_steps(self) -> int:
        return self.t_max_sec // self.step_sec


SETTINGS = Settings()
