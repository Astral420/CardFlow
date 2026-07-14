from app.config import settings
from app.tasks.extract import extract_batch
from app.tasks.hashing import hash_crop


def test_api_tasks_use_configured_celery_broker() -> None:
    assert extract_batch.app.conf.broker_url == settings.redis_url
    assert hash_crop.app.conf.broker_url == settings.redis_url
    assert extract_batch.app.conf.broker_url != "amqp://guest:**@localhost:5672//"
    assert hash_crop.app.conf.broker_url != "amqp://guest:**@localhost:5672//"
