#!/usr/bin/env bash
set -euo pipefail

# Pin versions instead of using "latest" (override via environment if needed)
ARGO_ROLLOUTS_VERSION="${ARGO_ROLLOUTS_VERSION:-v1.7.2}"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-2}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-4096}"

echo "=========================================================="
echo "SRE Progressive Canary Setup - Google Cloud Shell (\$0 Cost)"
echo "=========================================================="

# 1. Start Minikube inside Cloud Shell
echo "[1/7] Starting lightweight local Kubernetes cluster (Minikube)..."
if ! minikube status &>/dev/null; then
  minikube start --driver=docker --cpus="${MINIKUBE_CPUS}" --memory="${MINIKUBE_MEMORY}"
else
  echo "[+] Minikube is already running."
fi
minikube addons enable ingress
kubectl -n ingress-nginx wait --for=condition=ready pod \
  -l app.kubernetes.io/component=controller --timeout=180s

# 2. Build two DIFFERENT versions inside Minikube's Docker daemon
echo "[2/7] Building orders-service images (v1.0.0 stable, v2.0.0 canary)..."
eval "$(minikube docker-env)"
docker build -t orders-service:v1.0.0 --build-arg APP_VERSION=v1.0.0 -f app/Dockerfile .
docker build -t orders-service:v2.0.0 --build-arg APP_VERSION=v2.0.0 -f app/Dockerfile .

# 3. Install Argo Rollouts
echo "[3/7] Installing Argo Rollouts ${ARGO_ROLLOUTS_VERSION}..."
kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argo-rollouts -f "https://github.com/argoproj/argo-rollouts/releases/download/${ARGO_ROLLOUTS_VERSION}/install.yaml"
kubectl -n argo-rollouts rollout status deployment/argo-rollouts --timeout=120s

# 4. Install Argo Rollouts Kubectl Plugin
echo "[4/7] Installing Argo Rollouts CLI plugin..."
if ! command -v kubectl-argo-rollouts &>/dev/null; then
  curl -sLO "https://github.com/argoproj/argo-rollouts/releases/download/${ARGO_ROLLOUTS_VERSION}/kubectl-argo-rollouts-linux-amd64"
  chmod +x ./kubectl-argo-rollouts-linux-amd64
  sudo mv ./kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts
fi

# 5. Install Prometheus for Metric Analysis
echo "[5/7] Deploying Prometheus in monitoring namespace..."
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --set server.persistentVolume.enabled=false \
  --set alertmanager.enabled=false \
  --wait --timeout 5m

# 6. Apply SRE Canary Manifests
# NOTE: the Rollout pod template must carry these annotations, otherwise the
# default Prometheus chart will not scrape the app:
#   prometheus.io/scrape: "true"
#   prometheus.io/port: "8080"
#   prometheus.io/path: "/metrics"
echo "[6/7] Applying Canary Rollout & AnalysisTemplate..."
kubectl apply -f k8s/analysis-template.yaml
kubectl apply -f k8s/services.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/rollout.yaml

# 7. Verify
echo "[7/7] Verifying..."
kubectl get rollout orders-service
kubectl get ingress

echo "=========================================================="
echo "Setup Complete! (Minikube in Cloud Shell: no GKE charges)"
echo "=========================================================="
echo "To watch the rollout live, run:"
echo "   kubectl argo rollouts get rollout orders-service --watch"
echo ""
echo "To open the Argo Rollouts Web UI in Cloud Shell Web Preview:"
echo "   kubectl argo rollouts dashboard --port 8080"
echo "   (Then click Web Preview -> Preview on port 8080)"
echo "=========================================================="
