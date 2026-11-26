#!/usr/bin/env bash
set -euo pipefail
MODE=${1:-}
NS=online-boutique
SVCS="frontend cartservice checkoutservice currencyservice emailservice paymentservice productcatalogservice recommendationservice shippingservice adservice"
PROM=http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090


kubectl -n $NS delete scaledobject --all --ignore-not-found 2>/dev/null || true
kubectl -n $NS delete hpa --all --ignore-not-found
kubectl -n selfheal scale deploy selfheal-controller --replicas=0 2>/dev/null || true


for s in $SVCS; do kubectl -n $NS scale deploy $s --replicas=1; done
kubectl -n $NS rollout status deploy --timeout=180s >/dev/null

case $MODE in
  native) echo "Baseline 0: Kubernetes mac dinh (ReplicaSet + liveness probe)";;
  hpa)
    for s in $SVCS; do kubectl -n $NS autoscale deployment $s --cpu-percent=70 --min=1 --max=5; done
    kubectl -n $NS get hpa;;
  keda)
    
    if ! kubectl get crd scaledobjects.keda.sh >/dev/null 2>&1; then
      echo "LOI: chua cai KEDA (helm install keda kedacore/keda -n keda --create-namespace)" >&2; exit 1
    fi
    for s in $SVCS; do
      cat <<EOF | kubectl apply -f -
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: { name: $s, namespace: $NS }
spec:
  scaleTargetRef: { name: $s }
  pollingInterval: 15
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 5
  triggers:
    - type: cpu
      metricType: Utilization
      metadata: { value: "70" }
    - type: prometheus
      metadata:
        serverAddress: $PROM
        query: selfheal:ingress_rps:1m
        threshold: "100"
EOF
    done
    kubectl -n $NS get scaledobject;;
  agent) kubectl -n selfheal scale deploy selfheal-controller --replicas=1;;
  *) echo "usage: $0 native|hpa|keda|agent"; exit 1;;
esac