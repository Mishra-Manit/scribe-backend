import os
import redis
from rq import Worker, Queue, Connection

# Import your Flask app to ensure all functions are available
from app import final_together

listen = ['default']

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work() 