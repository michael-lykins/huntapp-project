import redis

def get_redis_client(redis_url: str) -> redis.Redis:
    return redis.from_url(redis_url)
