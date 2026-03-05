from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/historial/', views.historial_api, name='historial_api'),
    path('api/estado/', views.estado_api, name='estado_api'),  # Nueva ruta
]