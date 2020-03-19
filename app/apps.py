from django.apps import AppConfig
from django.core.cache import cache

from .quidem import Quidem

class QuidemConfiguration(AppConfig):
    cache.set('next_quidem_id', Quidem.INITIAL_SESSION_ID, None)
