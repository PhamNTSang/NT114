#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="${SCRIPT_DIR}/../grafana/dashboards"
EXTRA_VALUES=()

if [ -f "${SCRIPT_DIR}/alertmanager-slack.local.yaml" ]; then
  echo "Using local Alertmanager Slack override..."
  EXTRA_VALUES+=("-f" "${SCRIPT_DIR}/alertmanager-slack.local.yaml")
fi

echo "Installing Prometheus Stack"

# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f "${SCRIPT_DIR}/values.yaml" \
  "${EXTRA_VALUES[@]}" \
  --wait --timeout 10m

echo "Provisioning NT114 Grafana dashboards"
kubectl -n monitoring create configmap nt114-grafana-dashboards \
  --from-file=k8s-cluster-overview.json="${DASHBOARD_DIR}/k8s-cluster-overview.json" \
  --from-file=online-boutique-dashboard.json="${DASHBOARD_DIR}/online-boutique-dashboard.json" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n monitoring label configmap nt114-grafana-dashboards grafana_dashboard=1 --overwrite

echo "Prometheus Stack installed successfully"
echo ""
echo "Access Grafana:"
echo "  kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring"
echo "  URL: http://localhost:3000"
echo "  User: admin"
echo ""
echo "Access Prometheus:"
echo "  kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring"
echo "  URL: http://localhost:9090"
