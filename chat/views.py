import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.cache import cache
from .models import Conversacion, ConocimientoUAEMEX
from .services.ollama_service import OllamaService

ollama_service = OllamaService()

def index(request):
    if not request.session.session_key:
        request.session.create()
    ollama_ok = ollama_service.verificar_estado_rapido()
    context = {
        'session_id': request.session.session_key,
        'titulo': 'Asistente Virtual UAEMEX',
        'ollama_activo': ollama_ok
    }
    return render(request, 'chat/index.html', context)

@csrf_exempt
@require_POST
def chat_api(request):
    try:
        data = json.loads(request.body)
        mensaje = data.get('mensaje', '')
        session_id = data.get('session_id', request.session.session_key)

        # Obtener historial (solo última interacción para velocidad)
        ultima_conversacion = Conversacion.objects.filter(session_id=session_id).order_by('-fecha').first()
        historial_list = []
        if ultima_conversacion:
            historial_list = [{
                'pregunta': ultima_conversacion.pregunta,
                'respuesta': ultima_conversacion.respuesta
            }]

        # Buscar contexto (con caché)
        contexto = buscar_contexto_relevante_rapido(mensaje)
        
        # Consultar a Ollama
        respuesta = ollama_service.consultar_con_historial(mensaje, historial_list, contexto)

        # Guardar conversación (asíncrono - no bloquea)
        try:
            Conversacion.objects.create(
                session_id=session_id,
                pregunta=mensaje,
                respuesta=respuesta
            )
        except:
            pass  # Si falla el guardado, no afecta la respuesta

        return JsonResponse({'respuesta': respuesta})
    except Exception as e:
        print(f"Error en chat_api: {e}")
        return JsonResponse({'respuesta': 'Error interno del servidor'}, status=500)

def buscar_contexto_relevante_rapido(mensaje, limite=2):
    """
    Versión ultra-rápida de búsqueda de contexto
    """
    print(f"🔍 Buscando contexto rápido para: {mensaje}")
    
    # Intentar obtener de caché primero
    cache_key = f"contexto_{hash(mensaje)}"
    contexto_cache = cache.get(cache_key)
    if contexto_cache:
        print(f"⚡ Contexto desde caché")
        return contexto_cache
    
    palabras = mensaje.lower().split()
    palabras_clave = [p for p in palabras if len(p) > 3][:3]  # Solo 3 palabras máximo
    
    if not palabras_clave:
        return ""
    
    contextos = []
    
    # Búsqueda rápida en BD (solo un query)
    try:
        # Buscar por la palabra más relevante
        query = ConocimientoUAEMEX.objects.filter(
            contenido__icontains=palabras_clave[0]
        )[:limite]
        
        for conocimiento in query:
            contextos.append(conocimiento.contenido[:300])  # Texto más corto
            print(f"  ✅ Encontrado: {conocimiento.titulo[:30]}...")
    except Exception as e:
        print(f"Error en búsqueda BD: {e}")
    
    # Si no hay resultados, búsqueda web ultra-rápida
    if not contextos:
        print("🌐 Búsqueda web rápida...")
        resultado_web = buscar_en_uaemex_web_rapido(mensaje)
        if resultado_web:
            contextos.append(resultado_web)
    
    if not contextos:
        print("  ❌ Sin resultados")
        return ""
    
    resultado = "\n\n".join(contextos[:limite])
    cache.set(cache_key, resultado, 60 * 5)  # Cache por 5 minutos
    return resultado

def buscar_en_uaemex_web_rapido(consulta):
    """
    Versión ultra-rápida de búsqueda web (timeout reducido)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Solo buscar en 2 URLs clave
    urls_rapidas = [
        f"https://www.uaemex.mx/oferta-educativa/licenciaturas",
        "https://www.uaemex.mx"
    ]
    
    for url in urls_rapidas:
        try:
            print(f"  🌐 Visitando: {url[:50]}...")
            response = requests.get(url, headers=headers, timeout=3)  # Timeout 3s
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extraer solo párrafos relevantes
                parrafos = soup.find_all('p')[:5]
                textos = []
                
                for p in parrafos:
                    texto = p.get_text(strip=True)
                    if texto and len(texto) > 50 and any(p in texto.lower() for p in consulta.lower().split()[:2]):
                        textos.append(texto[:300])
                        if len(textos) >= 2:
                            break
                
                if textos:
                    return ' '.join(textos)
                    
        except Exception as e:
            continue
    
    return None

def historial_api(request):
    """
    API optimizada para historial
    """
    session_id = request.session.session_key
    conversaciones = Conversacion.objects.filter(session_id=session_id)[:10]  # Menos registros
    data = [{
        'pregunta': c.pregunta,
        'respuesta': c.respuesta[:100] + ('...' if len(c.respuesta) > 100 else ''),
        'fecha': c.fecha.strftime('%Y-%m-%d %H:%M')
    } for c in conversaciones]
    return JsonResponse({'historial': data})

def estado_api(request):
    """
    API de estado optimizada
    """
    cache_key = 'estado_ollama'
    estado = cache.get(cache_key)
    
    if not estado:
        ollama_ok = ollama_service.verificar_estado_rapido()
        modelos = ollama_service.listar_modelos()
        estado = {
            'ollama_activo': ollama_ok,
            'modelos_disponibles': len(modelos),
            'modelo_actual': ollama_service.model
        }
        cache.set(cache_key, estado, 30)  # Cache por 30 segundos
    
    return JsonResponse(estado)