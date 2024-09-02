from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from rq import Worker, Queue
from redis import Redis

from config.settings.base import REDIS_BACKEND


class Command(BaseCommand):
    help = 'Run RQ worker'

    def handle(self, *args, **kwargs):
        # Parse the REDIS_BACKEND URL
        redis_url = urlparse(REDIS_BACKEND)

        # Establish the Redis connection
        redis_conn = Redis(
            host=redis_url.hostname,
            port=redis_url.port,
            db=int(redis_url.path.lstrip('/')),
            password=redis_url.password
        )
        listen = ['default']

        # Create the queues
        queues = [Queue(name, connection=redis_conn) for name in listen]

        # Initialize and start the worker
        worker = Worker(queues, connection=redis_conn)
        worker.work()