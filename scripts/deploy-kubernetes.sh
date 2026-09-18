#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Kubernetes Deployment Script
# Automated deployment to Kubernetes cluster
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="magneetar"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/../kubernetes"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}MAGNEETAR — Kubernetes Deployment${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}[1/8] Checking prerequisites...${NC}"

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found. Please install kubectl first.${NC}"
    echo "  macOS: brew install kubectl"
    echo "  Linux: curl -LO \"https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl\""
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster.${NC}"
    echo "  Make sure your kubeconfig is configured correctly."
    exit 1
fi

echo -e "${GREEN}  ✓ kubectl installed and connected to cluster${NC}"

# Check if namespace exists
if kubectl get namespace $NAMESPACE &> /dev/null; then
    echo -e "${YELLOW}  ⚠ Namespace '$NAMESPACE' already exists${NC}"
else
    echo -e "${GREEN}  ✓ Ready to create namespace${NC}"
fi

echo ""

# Step 1: Create namespace
echo -e "${YELLOW}[2/8] Creating namespace...${NC}"
kubectl apply -f "${K8S_DIR}/namespace.yml"
echo -e "${GREEN}  ✓ Namespace created${NC}"
echo ""

# Step 2: Check secrets
echo -e "${YELLOW}[3/8] Checking secrets...${NC}"
if kubectl get secret magneetar-secrets -n $NAMESPACE &> /dev/null; then
    echo -e "${GREEN}  ✓ Secrets already exist${NC}"
else
    echo -e "${YELLOW}  ⚠ Secrets not found. Please create them first:${NC}"
    echo "    1. cp ${K8S_DIR}/secrets.yml.example ${K8S_DIR}/secrets.yml (gitignored) and fill in your actual credentials"
    echo "    2. Run: kubectl apply -f ${K8S_DIR}/secrets.yml   # the gitignored copy"
    echo ""
    echo -e "${YELLOW}  Do you want to continue without secrets? (y/n)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Step 3: Apply configuration
echo -e "${YELLOW}[4/8] Applying configuration...${NC}"
kubectl apply -f "${K8S_DIR}/configmap.yml"
echo -e "${GREEN}  ✓ ConfigMap applied${NC}"
echo ""

# Step 4: Deploy Redis
echo -e "${YELLOW}[5/8] Deploying Redis...${NC}"
kubectl apply -f "${K8S_DIR}/redis-deployment.yml"
echo -e "${GREEN}  ✓ Redis deployed${NC}"
echo ""

# Step 5: Deploy PostgreSQL
echo -e "${YELLOW}[6/8] Deploying PostgreSQL...${NC}"
kubectl apply -f "${K8S_DIR}/postgresql-statefulset.yml"
echo -e "${GREEN}  ✓ PostgreSQL deployed${NC}"
echo ""

# Step 6: Deploy application
echo -e "${YELLOW}[7/8] Deploying application...${NC}"
kubectl apply -f "${K8S_DIR}/server-deployment.yml"
kubectl apply -f "${K8S_DIR}/dashboard-deployment.yml"
echo -e "${GREEN}  ✓ Application deployed${NC}"
echo ""

# Step 7: Configure ingress
echo -e "${YELLOW}[8/8] Configuring ingress...${NC}"
kubectl apply -f "${K8S_DIR}/ingress.yml"
echo -e "${GREEN}  ✓ Ingress configured${NC}"
echo ""

# Wait for pods
echo -e "${YELLOW}Waiting for pods to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=postgresql -n $NAMESPACE --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=magneetar-server -n $NAMESPACE --timeout=120s 2>/dev/null || true
kubectl wait --for=condition=ready pod -l app=dashboard -n $NAMESPACE --timeout=120s 2>/dev/null || true
echo ""

# Show status
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Pods:"
kubectl get pods -n $NAMESPACE
echo ""
echo "Services:"
kubectl get services -n $NAMESPACE
echo ""
echo "Ingress:"
kubectl get ingress -n $NAMESPACE
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update DNS records:"
echo "   - api.magneetar.me → Ingress IP"
echo "   - app.magneetar.me → Ingress IP"
echo ""
echo "2. Configure TLS (Let's Encrypt):"
echo "   kubectl apply -f https://raw.githubusercontent.com/cert-manager/cert-manager/v1.13.0/deploy/manifests/00-crds.yaml"
echo "   kubectl apply -f https://raw.githubusercontent.com/cert-manager/cert-manager/v1.13.0/deploy/manifests/01-namespace.yaml"
echo "   kubectl apply -f https://raw.githubusercontent.com/cert-manager/cert-manager/v1.13.0/deploy/manifests/02-rbac.yaml"
echo "   kubectl apply -f https://raw.githubusercontent.com/cert-manager/cert-manager/v1.13.0/deploy/manifests/03-webhook.yaml"
echo ""
echo "3. Monitor deployment:"
echo "   kubectl get pods -n $NAMESPACE -w"
echo "   kubectl logs -f deployment/magneetar-server -n $NAMESPACE"
echo ""
echo -e "${GREEN}Magneetar is now running on Kubernetes! 🚀${NC}"
