# Magneetar Deployment Instructions

## Quick Start (5 minutes)

```bash
# 1. Update secrets with your credentials
cp kubernetes/secrets.yml.example kubernetes/secrets.yml
vim kubernetes/secrets.yml   # gitignored — never commit the filled copy

# 2. Deploy to Kubernetes
./scripts/deploy-kubernetes.sh

# 3. Verify deployment
kubectl get pods -n magneetar
```

---

## Prerequisites

### Required
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installed
- [Kubernetes cluster](https://kubernetes.io/docs/setup/) (EKS, GKE, AKS, or local)
- Docker (for building images)

### Optional
- [Helm](https://helm.sh/) for advanced deployments
- [cert-manager](https://cert-manager.io/) for TLS certificates

---

## Step-by-Step Deployment

### Step 1: Generate Secrets

```bash
# Generate secure keys
python3 -c "
import secrets
print(f\"MT_API_KEY={secrets.token_hex(32)}\")
print(f\"MT_DEVICE_KEY={secrets.token_hex(32)}\")
print(f\"MT_JWT_SECRET={secrets.token_hex(64)}\")
print(f\"MT_ENCRYPTION_KEY={secrets.token_hex(32)}\")
"
```

### Step 2: Update Secrets File

Copy the template (`kubernetes/secrets.yml.example`) to `kubernetes/secrets.yml`
(gitignored) and replace all `CHANGE_ME` values. NEVER edit the template in
place or commit a filled copy — that is how real secrets end up in git:

```yaml
stringData:
  database-url: "postgresql://magneetar:YOUR_PASSWORD@postgresql:5432/magneetar"
  postgres-user: "magneetar"
  postgres-password: "YOUR_STRONG_PASSWORD"
  api-key: "GENERATED_API_KEY"
  device-key: "GENERATED_DEVICE_KEY"
  jwt-secret: "GENERATED_JWT_SECRET"
  encryption-key: "GENERATED_ENCRYPTION_KEY"
```

### Step 3: Deploy

```bash
# Option A: Automated deployment
./scripts/deploy-kubernetes.sh

# Option B: Manual deployment
kubectl apply -f kubernetes/namespace.yml
kubectl apply -f kubernetes/secrets.yml   # the gitignored copy, not the template
kubectl apply -f kubernetes/configmap.yml
kubectl apply -f kubernetes/redis-deployment.yml
kubectl apply -f kubernetes/postgresql-statefulset.yml
kubectl apply -f kubernetes/server-deployment.yml
kubectl apply -f kubernetes/dashboard-deployment.yml
kubectl apply -f kubernetes/ingress.yml
```

### Step 4: Configure DNS

Point your domains to the ingress IP:

```bash
# Get ingress IP
kubectl get ingress -n magneetar

# Add DNS records
# api.magneetar.me → <INGRESS_IP>
# app.magneetar.me → <INGRESS_IP>
```

### Step 5: Verify Deployment

```bash
# Check pods
kubectl get pods -n magneetar

# Check services
kubectl get services -n magneetar

# Check logs
kubectl logs -f deployment/magneetar-server -n magneetar

# Test health endpoint
curl https://api.magneetar.me/health
```

---

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MT_ENVIRONMENT | production | Environment name |
| MT_MAX_DEVICES | 1 | Free tier device limit |
| MT_RETENTION_DAYS | 90 | Data retention period |
| MT_MAX_WS_CONNECTIONS | 250 | WebSocket connections per worker |
| MT_WRITE_BATCH_MS | 250 | Write batching interval |

### Scaling

```bash
# Scale server replicas
kubectl scale deployment magneetar-server --replicas=5 -n magneetar

# Scale dashboard replicas
kubectl scale deployment dashboard --replicas=3 -n magneetar
```

### Monitoring

```bash
# View metrics (operator only — requires a dashboard/admin JWT; the endpoint
# is deliberately NOT anonymous: it leaks user/device counts and which alert
# providers are configured)
TOKEN=$(curl -s -X POST https://api.magneetar.me/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"api_key":"<MT_API_KEY>"}' | jq -r .token)
curl -H "Authorization: Bearer $TOKEN" https://api.magneetar.me/metrics

# View logs
kubectl logs -f deployment/magneetar-server -n magneetar

# Port forward for local access
kubectl port-forward svc/magneetar-server 8000:8000 -n magneetar
```

---

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod <POD_NAME> -n magneetar

# Check logs
kubectl logs <POD_NAME> -n magneetar --previous
```

### Database Connection Issues

```bash
# Check PostgreSQL pod
kubectl get pods -l app=postgresql -n magneetar

# Test connection
kubectl exec -it <POSTGRESQL_POD> -n magneetar -- psql -U magneetar -d magneetar
```

### Redis Connection Issues

```bash
# Check Redis pod
kubectl get pods -l app=redis -n magneetar

# Test connection
kubectl exec -it <REDIS_POD> -n magneetar -- redis-cli ping
```

### Ingress Issues

```bash
# Check ingress status
kubectl describe ingress magneetar-ingress -n magneetar

# Check ingress controller logs
kubectl logs -f deployment/nginx-ingress-controller -n ingress-nginx
```

---

## Production Checklist

### Pre-Deployment
- [ ] Kubernetes cluster provisioned
- [ ] kubectl configured
- [ ] Secrets generated and configured
- [ ] DNS records configured
- [ ] TLS certificates ready

### Deployment
- [ ] Namespace created
- [ ] Secrets applied
- [ ] Redis deployed
- [ ] PostgreSQL deployed
- [ ] Server deployed
- [ ] Dashboard deployed
- [ ] Ingress configured

### Post-Deployment
- [ ] Health checks passing
- [ ] Metrics endpoint accessible
- [ ] WebSocket connections working
- [ ] Alert channels configured
- [ ] Monitoring setup

---

## Cloud Provider Specific

### AWS EKS

```bash
# Configure AWS CLI
aws eks update-kubeconfig --name magneetar-cluster --region us-east-1

# Deploy
./scripts/deploy-kubernetes.sh
```

### Google GKE

```bash
# Configure gcloud
gcloud container clusters get-credentials magneetar-cluster --region us-central1

# Deploy
./scripts/deploy-kubernetes.sh
```

### Azure AKS

```bash
# Configure Azure CLI
az aks get-credentials --resource-group magneetar-rg --name magneetar-cluster

# Deploy
./scripts/deploy-kubernetes.sh
```

### Local (minikube)

```bash
# Start minikube
minikube start

# Enable ingress addon
minikube addons enable ingress

# Deploy
./scripts/deploy-kubernetes.sh

# Access locally
minikube service magneetar-server -n magneetar
```

---

## Rollback

```bash
# Rollback server deployment
kubectl rollout undo deployment/magneetar-server -n magneetar

# Rollback dashboard deployment
kubectl rollout undo deployment/dashboard -n magneetar

# Check rollout status
kubectl rollout status deployment/magneetar-server -n magneetar
```

---

## Support

- Documentation: `docs/`
- Issues: GitHub Issues
- Email: support@magneetar.me

---

*Last Updated: August 2026*
