#!/usr/bin/env bash
# Bat cum EKS tren AWS
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE="${AWS_PROFILE:-kltn}" AWS_REGION="${AWS_REGION:-ap-southeast-2}"
aws sts get-caller-identity --query Account --output text 
terraform init -upgrade
terraform apply -auto-approve
aws eks update-kubeconfig --region "$AWS_REGION" --profile "$AWS_PROFILE" --name "$(terraform output -raw eks_cluster_name)" --alias kltn-eks
bash ../argocd/install/install.sh
kubectl apply -f ../argocd/applications/
