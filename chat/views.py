import json
import logging
import re
import time
import requests
import unicodedata
from bs4 import BeautifulSoup
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from .models import Conversacion, ConocimientoUAEMEX, Pregunta
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

        # MEMORIA DE BÚSQUEDA
        mensaje_busqueda = mensaje
        if ultimas_conversaciones:
            ultima = ultimas_conversaciones[-1]
            if len(mensaje.split()) <= 4 and "¡Hola!" not in ultima.respuesta:
                mensaje_busqueda = f"{ultima.pregunta} {mensaje}"

        # EJECUTAR BUSCADOR 3 TIER
        contexto = buscar_contexto_relevante_rapido(mensaje_busqueda, mensaje, limite=5)
        
        respuesta = ollama_service.consultar_con_historial(mensaje, historial_list, contexto)
            
        Conversacion.objects.create(session_id=session_id, pregunta=mensaje, respuesta=respuesta)
        logger.info("chat_api session=%s elapsed=%.2fs", session_id, time.time() - start_time)
        
        return JsonResponse({'respuesta': respuesta})
    except Exception as e:
        logger.exception("Error general en chat_api: %s", e)
        return JsonResponse({'respuesta': 'Error interno del servidor'}, status=500)

def buscar_contexto_relevante_rapido(mensaje_busqueda, mensaje_original, limite=5):
    cache_key = f"contexto_{hash(mensaje_busqueda)}"
    contexto_cache = cache.get(cache_key)
    if contexto_cache: return contexto_cache

    contextos = []

    # TIER 1: BÚSQUEDA POR FRASE EXACTA (Resuelve el problema de "Tiene algún costo?")
    mensaje_sin_acentos_orig = ''.join((c for c in unicodedata.normalize('NFD', mensaje_original) if unicodedata.category(c) != 'Mn'))
    frase_exacta = mensaje_sin_acentos_orig.lower().replace('?', '').replace('¿', '').strip()
    
    if len(frase_exacta) > 5:
        preguntas_exactas = list(Pregunta.objects.filter(pregunta__icontains=frase_exacta)[:2])
        for p in preguntas_exactas:
            contextos.append(f"FAQ EXACTA: Pregunta: '{p.pregunta}' Respuesta: '{p.respuesta}'")
        
        if contextos: return "\n\n".join(contextos) # Si encuentra la frase, se detiene aquí y no busca basura.

    # PREPARACIÓN PARA TIER 2 Y 3
    # Quitamos símbolos raros que estorban (como el/la)
    mensaje_busqueda = mensaje_busqueda.replace('/', ' ')
    mensaje_sin_acentos = ''.join((c for c in unicodedata.normalize('NFD', mensaje_busqueda) if unicodedata.category(c) != 'Mn'))
    palabras = mensaje_sin_acentos.lower().replace('?', '').replace('¿', '').replace('.', '').replace(',', '').split()
    
    # Agregamos nuevas palabras trampa a la lista negra
    stop_words = {
        'para', 'como', 'cuales', 'cual', 'sobre', 'este', 'esta', 'todo', 'pero', 'nivel', 
        'los', 'las', 'son', 'del', 'que', 'una', 'uno', 'universidad', 'uaemex', 'uaem', 
        'quien', 'cuando', 'donde', 'tiene', 'algun', 'hacer', 'actual', 'institucion', 
        'repite', 'repetir', 'anterior', 'puedes', 'decirme', 'okey', 'hola'
    }
    
    # LA MAGIA: Cortamos a 6 letras. "rectora" -> "rector". "rector" -> "rector". 
    palabras_clave = [p[:6] for p in palabras if len(p) > 2 and p not in stop_words]
    
    if not palabras_clave: palabras_clave = [p[:6] for p in palabras if len(p) > 2]
    palabras_clave = list(dict.fromkeys(palabras_clave))[:6] # Eliminar duplicados

    if not palabras_clave: return ""

    # TIER 2: BÚSQUEDA ESTRICTA (AND) - Deben estar TODAS las palabras
    try:
        filtro_and_preg = Q()
        for palabra in palabras_clave: filtro_and_preg &= (Q(pregunta__icontains=palabra) | Q(respuesta__icontains=palabra))
        preg_and = list(Pregunta.objects.filter(filtro_and_preg)[:3])

        filtro_and_pdf = Q()
        for palabra in palabras_clave: filtro_and_pdf &= (Q(contenido__icontains=palabra) | Q(titulo__icontains=palabra))
        pdf_and = list(ConocimientoUAEMEX.objects.filter(filtro_and_pdf).order_by('-fecha_actualizacion')[:3])

        for p in preg_and: contextos.append(f"FAQ: Pregunta: '{p.pregunta}' Respuesta: '{p.respuesta}'")
        for doc in pdf_and: contextos.append(f"DOC: {doc.contenido[:500]}")
        
        if contextos: return "\n\n".join(contextos)
    except: pass

    # TIER 3: BÚSQUEDA FLEXIBLE (OR) - Solo si falló lo anterior
    try:
        filtro_or_preg = Q()
        for palabra in palabras_clave: filtro_or_preg |= (Q(pregunta__icontains=palabra) | Q(respuesta__icontains=palabra))
        preg_or = list(Pregunta.objects.filter(filtro_or_preg)[:5])

        filtro_or_pdf = Q()
        for palabra in palabras_clave: filtro_or_pdf |= (Q(contenido__icontains=palabra) | Q(titulo__icontains=palabra))
        pdf_or = list(ConocimientoUAEMEX.objects.filter(filtro_or_pdf).order_by('-fecha_actualizacion')[:3])

        for p in preg_or: contextos.append(f"FAQ: Pregunta: '{p.pregunta}' Respuesta: '{p.respuesta}'")
        for doc in pdf_or: contextos.append(f"DOC: {doc.contenido[:500]}")
    except: pass

    if not contextos:
        res_web = buscar_en_uaemex_web_rapido(mensaje_busqueda)
        if res_web: contextos.append(res_web)

    return "\n\n".join(contextos)

def buscar_en_uaemex_web_rapido(consulta):
    headers = {'User-Agent': 'Mozilla/5.0'}
    urls_rapidas = []
    terminos_admision = ['admis', 'examen', 'convoc', 'preinscrip']
    if any(t in consulta.lower() for t in terminos_admision):
        urls_rapidas.append("https://nuevoingreso.uaemex.mx/")
    urls_rapidas.extend(["https://www.uaemex.mx/oferta-educativa/licenciaturas", "https://www.uaemex.mx"])
    for url in urls_rapidas:
        try:
            response = requests.get(url, headers=headers, timeout=3)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                parrafos = soup.find_all('p')[:5]
                textos = []
                for p in parrafos:
                    texto = p.get_text(strip=True)
                    if len(texto) > 50 and any(pal in texto.lower() for pal in consulta.lower().split()[:2]):
                        textos.append(texto[:300])
                        if len(textos) >= 2: break
                if textos: return ' '.join(textos)
        except: pass
    return None

def historial_api(request):
    session_id = request.session.session_key
    
    # Traemos las últimas 15 interacciones de esta sesión
    query_conversaciones = Conversacion.objects.filter(session_id=session_id).order_by('-fecha')[:15]
    conversaciones = list(query_conversaciones)
    
    # Las volteamos para que la más vieja salga arriba y la más nueva hasta abajo
    conversaciones.reverse() 
    
    data = [{
        'pregunta': c.pregunta, 
        'respuesta': c.respuesta, # <-- Ya mandamos la respuesta completa, sin recortes
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