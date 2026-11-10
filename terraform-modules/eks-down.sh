set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE="${AWS_PROFILE:-kltn}" AWS_REGION="${AWS_REGION:-ap-southeast-2}"
aws sts get-caller-identity --query Account --output text  
helm uninstall ingress-nginx -n ingress-nginx || true
kubectl delete svc -A --field-selector spec.type=LoadBalancer || true
sleep 60
terraform destroy -auto-approve