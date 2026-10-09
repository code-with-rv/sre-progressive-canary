# sre-progressive-canary
FastAPI "orders" microservice with Argo Rollouts progressive canary delivery (10%→25%→50%→100%) and Prometheus-based automated rollback on SLO breach (>1% errors). Runs locally on Minikube or GKE Autopilot.
