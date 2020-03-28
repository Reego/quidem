from django.contrib import admin
from django.urls import path
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

cache.set('next_quidem_id', 0, None)

@csrf_exempt
@require_POST
def create_quidem(request):
    return JsonResponse({
        'session_id': cache.get('next_quidem_id')
    })
    # Redirect user to quidem app / websocket endpoint

urlpatterns = [
    path('create/', create_quidem),
]
