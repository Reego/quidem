from django.contrib import admin
from django.urls import path

# receives post request
def create_quidem(request):
    pass
    # Redirect user to quidem app / websocket endpoint

urlpatterns = [
    path('admin/', admin.site.urls),
]
