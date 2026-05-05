#!/bin/bash
# 
set -e

# Khai bao phien ban ArgoCD 
ARGOCD_VERSION="v2.13.3"

echo "=== Installing ArgoCD ${ARGOCD_VERSION} ==="

# Tao namespace tren Kubernetes
# Neu da ton tai thi lenh nay se bo qua ma khong bao loi
echo "Creating argocd namespace..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -

# Tai va ap dung toan bo file cau hinh cua ArgoCD tu GitHub
echo "Applying ArgoCD install manifest..."
kubectl apply -n argocd -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

# Cho cac thanh phan cua ArgoCD khoi dong va chay thanh cong tren Kubernetes
echo "Waiting for ArgoCD deployments to be ready..."
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=300s
kubectl -n argocd rollout status deployment/argocd-applicationset-controller --timeout=300s
kubectl -n argocd rollout status deployment/argocd-redis --timeout=300s
kubectl -n argocd rollout status deployment/argocd-notifications-controller --timeout=300s
kubectl -n argocd rollout status deployment/argocd-dex-server --timeout=300s

echo ""
echo "=== ArgoCD Installation Complete ==="
echo ""

# Lay mat khau mac dinh cua admin
ADMIN_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)

# In mat khau ra man hinh
echo "Initial admin password: ${ADMIN_PASSWORD}"
echo ""

echo "=== Access Instructions ==="
echo "1. Port-forward to access ArgoCD UI:"
echo "   kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo ""
echo "2. Access the UI at: https://localhost:8080"
echo "   Username: admin"
echo "   Password: (printed above)"
echo ""
echo "3. Or use the ArgoCD CLI:"
echo "   argocd login localhost:8080 --username admin --password '${ADMIN_PASSWORD}' --insecure"
echo ""
echo "4. If using Ingress, access at: https://argocd.example.com"