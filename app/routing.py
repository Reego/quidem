# from django.urls import re_path
# from channels.auth import AuthMiddlewareStack
# from . import consumers

# websocket_urlpatterns = [
#     re_path(r'ws/chat/', consumers.ChatAppConsumer),
# ]

from django.urls import path, re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.sessions import SessionMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from . import consumers

application = ProtocolTypeRouter({
    'websocket': #AllowedHostsOriginValidator(
        URLRouter(
            [
                re_path(r'ws/quidem/.+/$', consumers.QuidemConsumer),
            ]
        )
})
