"""Redis client for auth session state: access-token revocation markers
and the refresh-token family registry (see app.token_store).

This is separate from app.celery_app's connection -- that one's owned by
the Celery library and points at redis_url/redis_result_backend_url
(DB 0/1). This one is a plain redis-py client on its own DB index
(redis_auth_url, DB 2 by default) so auth state doesn't share keyspace
with Celery's broker/backend traffic.
"""

import redis

from app.config import settings

redis_client = redis.Redis.from_url(settings.redis_auth_url, decode_responses=True)
