#!/bin/bash
# Runs on the instance: build both images from /opt/changeguard and (re)start the containers.
# The engine key lives in /etc/changeguard/env (root-only), created on first boot.
set -euo pipefail
cd /opt/changeguard

docker build -t changeguard-engine backend
docker build -t changeguard-web --build-arg CHANGEGUARD_API_URL=http://engine:8000 frontend

docker network inspect changeguard >/dev/null 2>&1 || docker network create changeguard
docker rm -f web engine >/dev/null 2>&1 || true

docker run -d --name engine --network changeguard --restart unless-stopped \
  -v changeguard-data:/data \
  --env-file /etc/changeguard/env \
  -e CHANGEGUARD_TRUST_PROXY_HEADERS=true \
  -e CHANGEGUARD_EXPOSE_DOCS=false \
  changeguard-engine

docker run -d --name web --network changeguard --restart unless-stopped \
  -p 80:3000 \
  --env-file /etc/changeguard/env \
  -e CHANGEGUARD_API_URL=http://engine:8000 \
  changeguard-web

docker image prune -f >/dev/null
echo "ChangeGuard is running."
