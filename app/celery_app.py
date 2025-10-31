"""
CaseScope 2026 v1.0.0 - Celery Application
"""

from celery import Celery
import logging

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery('casescope')

# Load configuration from config.py
celery_app.config_from_object('config.Config', namespace='CELERY')

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    broker_connection_retry_on_startup=True,
)

# Import tasks directly (instead of autodiscover)
import tasks

logger.info("Celery app initialized")
