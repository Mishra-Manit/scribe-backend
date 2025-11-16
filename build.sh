#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install your Python dependencies
pip install -r requirements.txt

# 2. Define a cache directory on Render's persistent disk
# We will tell Playwright to use this path
export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/.cache/playwright"

# 3. Check if the browser is already cached
# If the directory doesn't exist, install the browser
if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/chromium-1123" ]; then
  echo "Browser not found in cache. Installing..."
  
  # Install chromium WITHOUT --with-deps.
  # This relies on Render's base image having the system libraries.
  python -m playwright install chromium
else
  echo "Browser found in cache. Skipping installation."
fi