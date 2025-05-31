import os
import redis
from rq import Worker, Queue

# Import the tasks module instead of app
from tasks import generate_email

listen = ['default']

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
queue = Queue(connection=conn)

if __name__ == '__main__':
    worker = Worker([queue], connection=conn)
    worker.work() 