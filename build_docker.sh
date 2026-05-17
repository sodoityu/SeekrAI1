#!/bin/bash
# Build and run Docker container

set -e

IMAGE_NAME="unified-search"
VERSION="latest"

echo "======================================================================"
echo "🐳 Building Docker Image"
echo "======================================================================"

# Build Docker image
echo ""
echo "📦 Building image: $IMAGE_NAME:$VERSION"
echo ""
docker build -t $IMAGE_NAME:$VERSION .

echo ""
echo "======================================================================"
echo "✅ Docker image built successfully!"
echo "======================================================================"
echo ""
echo "🚀 Run the container:"
echo ""
echo "   # Basic run (enter credentials via UI)"
echo "   docker run -p 5500:5500 $IMAGE_NAME:$VERSION"
echo ""
echo "   # With environment variables"
echo "   docker run -p 5500:5500 \\"
echo "     -e JIRA_EMAIL='your-email@redhat.com' \\"
echo "     -e JIRA_API_TOKEN='your-token' \\"
echo "     -e RH_API_OFFLINE_TOKEN='your-sfdc-token' \\"
echo "     $IMAGE_NAME:$VERSION"
echo ""
echo "   # With persistent credentials"
echo "   docker run -p 5500:5500 \\"
echo "     -v $(pwd)/.saved_credentials.json:/app/.saved_credentials.json \\"
echo "     $IMAGE_NAME:$VERSION"
echo ""
echo "   # Detached mode"
echo "   docker run -d -p 5500:5500 --name unified-search $IMAGE_NAME:$VERSION"
echo ""
echo "🌐 Access: http://localhost:5500"
echo ""
echo "📤 Push to Docker Hub:"
echo "   docker tag $IMAGE_NAME:$VERSION sodoityu/unified-search:$VERSION"
echo "   docker push sodoityu/unified-search:$VERSION"
echo ""
