#!/bin/bash
# Helper script to deploy and manage the Payment A/B test deployment
#
# Usage:
#   ./test-payment-ab.sh deploy    - Deploy the three services
#   ./test-payment-ab.sh delete    - Delete the three services
#   ./test-payment-ab.sh status    - Show status of the services
#   ./test-payment-ab.sh logs      - Tail logs from all services
#   ./test-payment-ab.sh restart   - Restart all deployments

set -e

MANIFEST="test-payment-ab-deployment.yaml"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

function deploy() {
    echo -e "${BLUE}🚀 Deploying Payment A/B and Checkout test services...${NC}"
    kubectl apply -f "$MANIFEST"

    echo ""
    echo -e "${GREEN}✅ Deployment initiated${NC}"
    echo ""
    echo "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod -l app=payment --timeout=60s || true
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=checkout --timeout=60s || true

    echo ""
    status
}

function delete_services() {
    echo -e "${YELLOW}🗑️  Deleting Payment A/B and Checkout test services...${NC}"
    kubectl delete -f "$MANIFEST" --ignore-not-found=true

    echo ""
    echo -e "${GREEN}✅ Services deleted${NC}"
}

function status() {
    echo -e "${BLUE}📊 Service Status:${NC}"
    echo ""

    echo -e "${BLUE}Secrets:${NC}"
    kubectl get secrets payment-va-secret payment-vb-secret 2>/dev/null || echo "  No secrets found"
    echo ""

    echo -e "${BLUE}Services:${NC}"
    kubectl get svc payment-va payment-vb checkout 2>/dev/null || echo "  No services found"
    echo ""

    echo -e "${BLUE}Deployments:${NC}"
    kubectl get deployments payment-va payment-vb checkout 2>/dev/null || echo "  No deployments found"
    echo ""

    echo -e "${BLUE}Pods:${NC}"
    kubectl get pods -l 'app in (payment),app.kubernetes.io/component in (checkout)' -o wide 2>/dev/null || echo "  No pods found"
}

function logs() {
    echo -e "${BLUE}📜 Tailing logs from all services (Ctrl+C to stop)...${NC}"
    echo ""

    # Get pod names
    VA_POD=$(kubectl get pods -l app=payment,version=vA -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    VB_POD=$(kubectl get pods -l app=payment,version=vB -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    CHECKOUT_POD=$(kubectl get pods -l app.kubernetes.io/component=checkout -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$VA_POD" ] && [ -z "$VB_POD" ] && [ -z "$CHECKOUT_POD" ]; then
        echo -e "${RED}❌ No pods found${NC}"
        exit 1
    fi

    # Tail logs from all pods
    (
        [ -n "$VA_POD" ] && kubectl logs -f "$VA_POD" --prefix=true 2>/dev/null &
        [ -n "$VB_POD" ] && kubectl logs -f "$VB_POD" --prefix=true 2>/dev/null &
        [ -n "$CHECKOUT_POD" ] && kubectl logs -f "$CHECKOUT_POD" --prefix=true 2>/dev/null &
        wait
    )
}

function restart() {
    echo -e "${BLUE}🔄 Restarting deployments...${NC}"
    kubectl rollout restart deployment payment-va payment-vb checkout 2>/dev/null

    echo ""
    echo "Waiting for rollout to complete..."
    kubectl rollout status deployment payment-va --timeout=60s || true
    kubectl rollout status deployment payment-vb --timeout=60s || true
    kubectl rollout status deployment checkout --timeout=60s || true

    echo ""
    echo -e "${GREEN}✅ Restart complete${NC}"
    echo ""
    status
}

function test_routing() {
    echo -e "${BLUE}🧪 Testing Payment A/B routing...${NC}"
    echo ""

    # Get checkout pod
    CHECKOUT_POD=$(kubectl get pods -l app.kubernetes.io/component=checkout -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$CHECKOUT_POD" ]; then
        echo -e "${RED}❌ Checkout pod not found${NC}"
        exit 1
    fi

    echo "Checkout pod: $CHECKOUT_POD"
    echo ""
    echo "Testing connectivity to payment services..."

    # Test payment-va
    echo -n "  payment-va:8080 ... "
    kubectl exec "$CHECKOUT_POD" -- nc -zv payment-va 8080 2>&1 | grep -q "succeeded" && echo -e "${GREEN}✅${NC}" || echo -e "${RED}❌${NC}"

    # Test payment-vb
    echo -n "  payment-vb:8080 ... "
    kubectl exec "$CHECKOUT_POD" -- nc -zv payment-vb 8080 2>&1 | grep -q "succeeded" && echo -e "${GREEN}✅${NC}" || echo -e "${RED}❌${NC}"

    echo ""
    echo -e "${BLUE}💡 Tip: Set paymentFailure flag in flagd to route traffic:${NC}"
    echo "  - 'off' (0)    → 100% to payment-va"
    echo "  - '10%' (0.1)  → 10% to payment-vb, 90% to payment-va"
    echo "  - '50%' (0.5)  → 50% to payment-vb, 50% to payment-va"
    echo "  - '100%' (1)   → 100% to payment-vb"
}

case "$1" in
    deploy)
        deploy
        ;;
    delete)
        delete_services
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    restart)
        restart
        ;;
    test)
        test_routing
        ;;
    *)
        echo "Usage: $0 {deploy|delete|status|logs|restart|test}"
        echo ""
        echo "Commands:"
        echo "  deploy   - Deploy the three test services"
        echo "  delete   - Delete the three test services"
        echo "  status   - Show status of all resources"
        echo "  logs     - Tail logs from all services"
        echo "  restart  - Restart all deployments (e.g., after rebuilding images)"
        echo "  test     - Test payment service routing"
        exit 1
        ;;
esac
