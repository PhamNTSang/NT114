import os

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
APP_NAMESPACE = os.getenv("APP_NAMESPACE", "online-boutique")

LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "24"))
QUERY_STEP = os.getenv("QUERY_STEP", "5m")
CONTAMINATION_FACTOR = float(os.getenv("CONTAMINATION_FACTOR", "0.05"))
MIN_DATA_POINTS = int(os.getenv("MIN_DATA_POINTS", "10"))
STD_DEVIATION_MULTIPLIER = float(os.getenv("STD_DEVIATION_MULTIPLIER", "2.0"))
PROMETHEUS_TIMEOUT = int(os.getenv("PROMETHEUS_TIMEOUT", "30"))

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

METRICS_QUERIES = {
    "app_cpu_usage": {
        "query": (
            'sum(rate(container_cpu_usage_seconds_total{'
            f'namespace="{APP_NAMESPACE}",container!="",image!=""'
            '}[5m])) by (namespace, pod)'
        ),
        "description": f"CPU usage by pod in namespace {APP_NAMESPACE}",
    },
    "app_memory_usage": {
        "query": (
            'sum(container_memory_working_set_bytes{'
            f'namespace="{APP_NAMESPACE}",container!="",image!=""'
            '}) by (namespace, pod)'
        ),
        "description": f"Memory usage by pod in namespace {APP_NAMESPACE}",
    },
    "node_cpu": {
        "query": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "description": "Node CPU usage percentage",
    },
    "node_memory": {
        "query": '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
        "description": "Node memory usage percentage",
    },
}
