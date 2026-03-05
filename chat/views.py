import json
import uuid
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Conversacion, ConocimientoUAEMEX
from .services.ollama_service import OllamaService

# Instancia global del servicio
ollama_service = OllamaService()

def index(request):
    """Vista principal del chat"""
    if not request.session.session_key:
        request.session.create()
    
    # Verificar estado de Ollama
    ollama_ok = ollama_service.verificar_estado()
    
    context = {
        'session_id': request.session.session_key,
        'titulo': 'Asistente Virtual UAEMEX',
        'ollama_activo': ollama_ok
    }
    return render(request, 'chat/index.html', context)

@csrf_exempt
@require_POST
def chat_api(request):
    """API para procesar mensajes con Llama 3.2"""
    try:
        data = json.loads(request.body)
        mensaje = data.get('mensaje', '')
        session_id = data.get('session_id', request.session.session_key)
        
        # Buscar contexto relevante en la BD
        contexto = buscar_contexto_relevante(mensaje)
        
        # Consultar a Llama 3.2
        respuesta = ollama_service.consultar(mensaje, contexto)
        
        # Guardar conversación
        Conversacion.objects.create(
            session_id=session_id,
            pregunta=mensaje,
            respuesta=respuesta
        )
        
        return JsonResponse({
            'respuesta': respuesta,
            'session_id': session_id,
            'contexto_usado': bool(contexto)
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'respuesta': 'Lo siento, ocurrió un error al procesar tu mensaje.'
        }, status=500)

def buscar_contexto_relevante(mensaje, limite=3):
    """
    Busca información relevante en la BD para dar contexto a la IA
    """
    # Palabras clave simples (mejorable)
    palabras = mensaje.lower().split()
    
    contextos = []
    
    for palabra in palabras[:5]:  # Solo primeras 5 palabras
        if len(palabra) < 4:  # Ignorar palabras muy cortas
            continue
            
        conocimientos = ConocimientoUAEMEX.objects.filter(
            contenido__icontains=palabra
        )[:limite]
        
        for conocimiento in conocimientos:
            if conocimiento.contenido not in contextos:
                contextos.append(conocimiento.contenido[:500])
    
    return "\n\n".join(contextos[:limite])

def historial_api(request):
    """API para obtener historial de conversaciones"""
    session_id = request.session.session_key
    conversaciones = Conversacion.objects.filter(session_id=session_id)[:20]
    
    data = [{
        'pregunta': c.pregunta,
        'respuesta': c.respuesta,
        'fecha': c.fecha.strftime('%Y-%m-%d %H:%M')
    } for c in conversaciones]
    
    return JsonResponse({'historial': data})

def estado_api(request):
    """API para verificar el estado del sistema"""
    ollama_ok = ollama_service.verificar_estado()
    modelos = ollama_service.listar_modelos()
    
    return JsonResponse({
        'ollama_activo': ollama_ok,
        'modelos_disponibles': modelos,
        'modelo_actual': ollama_service.model
    })