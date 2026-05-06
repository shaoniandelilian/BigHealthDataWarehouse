#!/usr/bin/env bash
# deploy.sh — Build image in minikube and deploy to K8s
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Switching to minikube docker daemon..."
eval $(minikube docker-env)

echo "==> Building image..."
docker build -t product-research:latest .

echo "==> Applying K8s manifests..."
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

echo "==> Restarting deployment..."
kubectl rollout restart deployment/product-research
kubectl rollout status deployment/product-research --timeout=120s

NODE_IP=$(minikube ip)
echo "==> Deployed! Access at http://${NODE_IP}:30501"
