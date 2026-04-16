from django.urls import path
from . import views
from .views import memoria_usuario_api, reiniciar_memoria_api

urlpatterns = [
    path('', views.index, name='index'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/historial/', views.historial_api, name='historial_api'),
    path('api/estado/', views.estado_api, name='estado_api'),
    path('api/health/', views.health_api, name='health_api'),
    path('api/memoria/', memoria_usuario_api, name='memoria_usuario'),
    path('api/memoria/reiniciar/', reiniciar_memoria_api, name='reiniciar_memoria'),
]
