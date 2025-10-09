# worker/worker_app/main.py

import os
import logging
import time

from lib.search.events_bootstrap import events_bootstrap
from lib.services.elastic_client import get_elasticsearch_client
from lib.services.redis_conn import get_redis_client
from rq import Worker, Queue, Connection
from redis import Redis

log = logging.getLogger("huntapp.worker")


es = get_elasticsearch_client(
    host=os.environ["ELASTIC_SEARCH_HOST"],
    api_key=os.environ["ELASTIC_SEARCH_API_KEY"]
)

redis_client = get_redis_client(os.environ["REDIS_URL"])

def main():
    log.info("Starting worker application")
    events_bootstrap(es, redis_client)
    log.info("Worker application started")

def main_loop():
    while True:
        log.info("Worker heartbeat")
        time.sleep(10)

def run():
    redis = Redis(host="redis", port=6379)
    with Connection(redis):
        Worker([Queue("images")]).work()

if __name__ == "__main__":
    main_loop()