#!/usr/bin/env bash
# Dung lai toan bo stack tren kind 
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== 1. Tao cum kind ==="
kind get clusters | grep -q '^selfheal$' || kind create cluster --config "$ROOT/kubernetes/local/kind-config.yaml"

echo "=== 2. Helm repos ==="
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

echo "=== 3. Prometheus stack ==="
PROM_EXTRA_VALUES="$ROOT/kubernetes/local/prometheus-lite-values.yaml" \
  bash "$ROOT/monitoring/prometheus/install.sh"

echo "=== 4. Ingress NGINX ==="
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace \
  -f "$ROOT/kubernetes/ingress/ingress-nginx-values.yaml" \
  --set controller.service.type=NodePort --wait

echo "=== 5. metrics-server  ==="
helm upgrade --install metrics-server metrics-server/metrics-server -n kube-system \
  --set 'args={--kubelet-insecure-tls}' --wait

echo "=== 6. Online Boutique va Ingress ==="
kubectl create namespace online-boutique --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k "$ROOT/kubernetes/online-boutique"
kubectl apply -f "$ROOT/kubernetes/ingress/ingress.yaml"
kubectl -n online-boutique wait --for=condition=available deploy --all --timeout=600s

echo "=== 7. Chaos Mesh  ==="
MSYS_NO_PATHCONV=1 helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
  --set controllerManager.replicaCount=1 \
  --set dashboard.create=false \
    --version 2.7.2 --wait --timeout 20m

echo "=== 8. Recording rules + Locust  ==="
kubectl apply -f "$ROOT/monitoring/prometheus/selfheal-rules.yaml"
kubectl apply -f "$ROOT/chaos-testing/locust/k8s/"
kubectl -n loadtest scale deploy/locust-worker --replicas=1  

echo "Xong. Prometheus: kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090"
echo "Tam dung cum (nha RAM): docker stop selfheal-control-plane | bat lai: docker start selfheal-control-plane"