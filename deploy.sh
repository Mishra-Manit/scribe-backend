#!/bin/bash
set -e

# Derive paths from this scripts location so it works on any host/user
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICES="scribe-web scribe-worker"

echo "========================================"
echo "Starting Deployment: Scribe Backend"
echo "Project: $PROJECT_DIR"
echo "========================================"

echo "Stopping services..."
sudo systemctl stop $SERVICES

echo "Pulling latest code..."
cd "$PROJECT_DIR"
git pull origin main

echo "Checking for new dependencies..."
source "$PROJECT_DIR/venv/bin/activate"
pip install -q -r "$PROJECT_DIR/requirements.txt"

echo "Restarting services..."
sudo systemctl start $SERVICES

echo "Waiting 5 seconds for startup..."
sleep 5

echo "Deployment complete. Status:"
sudo systemctl status $SERVICES --no-pager
