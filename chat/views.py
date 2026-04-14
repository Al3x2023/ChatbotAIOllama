import json
import logging
import re
import time
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.db import connection
from .models import Conversacion
from .services.ollama_service import OllamaService

logger = logging.getLogger(__name__)
ollama_service = OllamaService()

@ensure_csrf_cookie
def index(request):
    if not request.session.session_key:
        request.session.create()
    return render(request, 'chat/index.html', {
        'session_id': request.session.session_key,
        'titulo': 'Asistente Virtual UAEMEX',
        'ollama_activo': ollama_service.verificar_estado_rapido()
    })

@require_POST
def chat_api(request):
    start_time = time.time()
    try:
        data = json.loads(request.body)
        mensaje = (data.get('mensaje', '') or '').strip()
        session_id = data.get('session_id', request.session.session_key)
        
        if not mensaje: return JsonResponse({'respuesta': 'Tu mensaje está vacío.'}, status=400)

        # INTERCEPTOR DE SALUDOS BÁSICOS EN PYTHON
        mensaje_limpio_saludo = re.sub(r'[^\w\s]', '', mensaje.lower()).strip()
        if mensaje_limpio_saludo in {'hola', 'buenas', 'buenos dias', 'buenas tardes', 'buenas noches', 'saludos', 'que tal', 'hey'}:
            resp = "¡Hola! Soy el Asistente Virtual Oficial de la UAEMex. ¿En qué trámite o duda puedo ayudarte hoy?"
            Conversacion.objects.create(session_id=session_id, pregunta=mensaje, respuesta=resp)
            return JsonResponse({'respuesta': resp})

        # HISTORIAL DE CONVERSACIÓN
        query_conversaciones = Conversacion.objects.filter(session_id=session_id).order_by('-fecha')[:3]
        ultimas_conversaciones = list(query_conversaciones)
        ultimas_conversaciones.reverse() 
        
        historial_list = []
        for conv in ultimas_conversaciones:
            if "¡Hola! Soy el Asistente" not in conv.respuesta:
                historial_list.append({'pregunta': conv.pregunta, 'respuesta': conv.respuesta})

        # DELEGAMOS LA BÚSQUEDA Y LA IA AL SERVICIO (Dejamos contexto vacío para que Ollama busque)
        respuesta = ollama_service.consultar_con_historial(mensaje, historial_list, contexto="")
            
        Conversacion.objects.create(session_id=session_id, pregunta=mensaje, respuesta=respuesta)
        logger.info("chat_api session=%s elapsed=%.2fs", session_id, time.time() - start_time)
        
        return JsonResponse({'respuesta': respuesta})
    except Exception as e:
        logger.exception("Error general en chat_api: %s", e)
        return JsonResponse({'respuesta': 'Error interno del servidor'}, status=500)

def historial_api(request):
    session_id = request.session.session_key
    
    query_conversaciones = Conversacion.objects.filter(session_id=session_id).order_by('-fecha')[:15]
    conversaciones = list(query_conversaciones)
    conversaciones.reverse() 
    
    data = [{
        'pregunta': c.pregunta, 
        'respuesta': c.respuesta, 
        'fecha': c.fecha.strftime('%Y-%m-%d %H:%M')
    } for c in conversaciones]
    
    return JsonResponse({'historial': data})

def estado_api(request):
    cache_key = 'estado_ollama'
    estado = cache.get(cache_key)
    if not estado:
        estado = {'ollama_activo': ollama_service.verificar_estado_rapido(), 'modelos_disponibles': len(ollama_service.listar_modelos()), 'modelo_actual': ollama_service.model}
        cache.set(cache_key, estado, 30)
    return JsonResponse(estado)

def health_api(request):
    db_ok = True
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1"); cursor.fetchone()
    except: db_ok = False
    return JsonResponse({'status': 'ok' if db_ok else 'degraded', 'db_ok': db_ok, 'ollama_ok': ollama_service.verificar_estado_rapido()}, status=200 if db_ok else 503)