# Worker Dyno Deployment Guide

## Prerequisites
- Heroku CLI installed
- Heroku app already created

## Setup Steps

### 1. Add Redis Addon to Heroku
```bash
heroku addons:create heroku-redis:mini -a your-app-name
```

### 2. Deploy the Updated Code
```bash
git add .
git commit -m "Add worker dyno support with RQ"
git push heroku main
```

### 3. Scale Up the Worker Dyno
```bash
heroku ps:scale worker=1 -a your-app-name
```

### 4. Verify Worker is Running
```bash
heroku ps -a your-app-name
heroku logs --tail -a your-app-name
```

## How It Works

1. **Web Request Flow**:
   - User submits email generation request
   - Flask app queues the job in Redis
   - Returns immediately with job ID (< 1 second)

2. **Worker Processing**:
   - Worker dyno picks up job from Redis queue
   - Processes email generation (can take minutes)
   - Saves result to Firebase
   - User sees email in dashboard

## Monitoring

### Check Worker Logs
```bash
heroku logs --tail --dyno=worker -a your-app-name
```

### Check Queue Status
You can add a status endpoint to monitor queue:
```python
@app.route('/queue-status', methods=['GET'])
def queue_status():
    return jsonify({
        'queued_jobs': len(q),
        'failed_jobs': len(q.failed_job_registry),
        'started_jobs': len(q.started_job_registry)
    })
```

## Cost Breakdown
- Worker Dyno: ~$7/month (Hobby tier)
- Redis Mini: ~$15/month
- Total: ~$22/month additional

## Troubleshooting

### Worker Not Processing Jobs
1. Check if worker is running: `heroku ps`
2. Check Redis connection: `heroku config`
3. Check worker logs for errors

### Jobs Failing
1. Check failed job registry
2. Increase job timeout if needed
3. Check for memory issues

## Benefits
- No more 30-second timeouts
- Process multiple professors in parallel
- Automatic retry on failure
- Better user experience 