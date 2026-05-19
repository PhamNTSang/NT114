#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRA_VALUES=()

if [ -f "${SCRIPT_DIR}/alertmanager-slack.local.yaml" ]; then
  echo "Using local Alertmanager Slack override..."
  EXTRA_VALUES+=("-f" "${SCRIPT_DIR}/alertmanager-slack.local.yaml")
fi

echo "=== Installing Prometheus Stack ==="


helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update


helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f "${SCRIPT_DIR}/values.yaml" \
  "${EXTRA_VALUES[@]}" \
  --set grafana.persistence.enabled=false

echo "=== Prometheus Stack installed successfully ==="
echo ""
echo "Access Grafana:"
echo "  kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring"
echo "  URL: http://localhost:3000"
echo "  User: admin"
echo ""
echo "Access Prometheus:"
echo "  kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring"
echo "  URL: http://localhost:9090"
