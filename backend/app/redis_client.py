import redis

from app.config import settings

redis_client = redis.Redis.from_url(settings.redis_auth_url, decode_responses=True)
