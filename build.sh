#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install your Python dependencies
pip install -r requirements.txt

python -m playwright install chromium