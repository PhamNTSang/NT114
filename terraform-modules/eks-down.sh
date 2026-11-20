#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE="${AWS_PROFILE:-kltn}" AWS_REGION="${AWS_REGION:-ap-southeast-2}"
aws sts get-caller-identity --query Account --output text
helm --kube-context kltn-eks uninstall ingress-nginx -n ingress-nginx || true
kubectl --context kltn-eks get svc -A \
  -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' \
  | while read -r ns name; do kubectl --context kltn-eks -n "$ns" delete svc "$name"; done || true
sleep 60
terraform destroy -auto-approve