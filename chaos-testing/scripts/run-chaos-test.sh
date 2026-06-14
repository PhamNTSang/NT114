#!/bin/bash
set -e

echo "============================================="
echo "  Chaos Testing - Cloud Native Monitoring"
echo "============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NAMESPACE=${1:-online-boutique}

echo -e "${YELLOW}Phase 0: Pre-cleanup (Dọn dẹp tài nguyên cũ)${NC}"
echo "Đang xóa các Job cũ nếu có..."
kubectl delete job cpu-stress-test -n ${NAMESPACE} --ignore-not-found
kubectl delete job memory-stress-test -n ${NAMESPACE} --ignore-not-found
sleep 2

echo -e "${YELLOW}Phase 1: Baseline Monitoring (2 minutes)${NC}"
echo "Recording baseline metrics before stress test..."
echo "Check Grafana dashboard at: http://grafana.example.com"
sleep 5

echo ""
echo -e "${YELLOW}Phase 2: CPU Stress Test${NC}"
echo "Applying CPU stress test..."
kubectl apply -f cpu-stress-test.yaml
echo -e "${GREEN}CPU stress test started (5 minutes duration)${NC}"
echo "Monitor the following:"
echo "  - Grafana: CPU usage spike"
echo "  - Prometheus alerts: HighNodeCPU / HighPodCPU"
echo "  - AI anomaly detection: Check Slack/Telegram for dynamic alerts"
echo ""
echo "Waiting for CPU stress test to complete..."
kubectl wait --for=condition=complete job/cpu-stress-test -n ${NAMESPACE} --timeout=400s || true

echo ""
echo -e "${YELLOW}Phase 3: Recovery Period (2 minutes)${NC}"
echo "Allowing system to recover..."
sleep 120

echo ""
echo -e "${YELLOW}Phase 4: Memory Stress Test${NC}"
echo "Applying memory stress test..."
kubectl apply -f memory-stress-test.yaml
echo -e "${GREEN}Memory stress test started (5 minutes duration)${NC}"
echo "Monitor the following:"
echo "  - Grafana: Memory usage spike"
echo "  - Prometheus alerts: HighNodeMemory / HighPodMemory"
echo "  - AI anomaly detection: Check Slack/Telegram for dynamic alerts"
echo ""
echo "Waiting for memory stress test to complete..."
kubectl wait --for=condition=complete job/memory-stress-test -n ${NAMESPACE} --timeout=400s || true

echo ""
echo -e "${YELLOW}Phase 5: Cleanup${NC}"
kubectl delete job cpu-stress-test -n ${NAMESPACE} --ignore-not-found
kubectl delete job memory-stress-test -n ${NAMESPACE} --ignore-not-found
echo -e "${GREEN}Cleanup complete${NC}"

echo ""
echo "============================================="
echo -e "${GREEN}  Chaos Testing Complete!${NC}"
echo "============================================="
echo ""
