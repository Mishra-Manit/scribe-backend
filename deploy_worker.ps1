# Heroku Worker Deployment Script

Write-Host "Deploying Worker Dyno Setup to Heroku..." -ForegroundColor Green

# Check if we're in the pythonserver directory
if (-not (Test-Path "app.py")) {
    Write-Host "Error: Must run this script from the pythonserver directory" -ForegroundColor Red
    exit 1
}

# Get Heroku app name
$appName = Read-Host "Enter your Heroku app name"

Write-Host "`nStep 1: Adding Redis addon..." -ForegroundColor Yellow
heroku addons:create heroku-redis:mini -a $appName
if ($LASTEXITCODE -ne 0) {
    Write-Host "Note: Redis addon might already exist or there was an error" -ForegroundColor Yellow
}

Write-Host "`nStep 2: Deploying code to Heroku..." -ForegroundColor Yellow
git add .
git commit -m "Add worker dyno support with RQ for email generation"
git push heroku main

Write-Host "`nStep 3: Scaling worker dyno..." -ForegroundColor Yellow
heroku ps:scale worker=1 -a $appName

Write-Host "`nStep 4: Checking deployment status..." -ForegroundColor Yellow
heroku ps -a $appName

Write-Host "`nDeployment complete!" -ForegroundColor Green
Write-Host "You can monitor logs with: heroku logs --tail -a $appName" -ForegroundColor Cyan
Write-Host "Monitor worker logs with: heroku logs --tail --dyno=worker -a $appName" -ForegroundColor Cyan 