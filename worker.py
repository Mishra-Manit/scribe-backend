import os
import redis
from rq import Worker, Queue, Connection

# Import the tasks module instead of app
from tasks import generate_email

listen = ['default']

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work() 