import os
import redis
from rq import Worker, Queue
import ssl

# Import the tasks module instead of app
from tasks import generate_email

listen = ['default']

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Configure Redis connection with SSL
if redis_url.startswith('rediss://'):
    # Create an SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    conn = redis.from_url(redis_url, ssl_cert_reqs=None)
else:
    conn = redis.from_url(redis_url)

queue = Queue(connection=conn)

if __name__ == '__main__':
    worker = Worker([queue], connection=conn)
    worker.work() 