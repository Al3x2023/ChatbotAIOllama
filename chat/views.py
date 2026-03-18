import json
import logging
import re
import time
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from .models import Conversacion, ConocimientoUAEMEX
from .services.ollama_service import OllamaService

logger = logging.getLogger(__name__)
ollama_service = OllamaService()
PATRON_MONTO = re.compile(r'(?<!\d)(\d{2,5})(?:[.,]\d{1,2})?\s*(?:pesos|mxn)?', re.IGNORECASE)

@ensure_csrf_cookie
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
    start_time = time.time()
    try:
        data = json.loads(request.body)
        mensaje = (data.get('mensaje', '') or '').strip()
        session_id = data.get('session_id', request.session.session_key)
        if not mensaje:
            return JsonResponse({'respuesta': 'Tu mensaje está vacío.'}, status=400)
        if len(mensaje) > 1000:
            return JsonResponse({'respuesta': 'Tu mensaje es demasiado largo.'}, status=400)

        throttle_key = f"chat_throttle_{session_id}"
        throttle_count = cache.get(throttle_key, 0)
        if throttle_count >= 25:
            return JsonResponse({'respuesta': 'Demasiadas solicitudes. Intenta en un minuto.'}, status=429)
        cache.set(throttle_key, throttle_count + 1, 60)

        ultima_conversacion = Conversacion.objects.filter(session_id=session_id).order_by('-fecha').first()
        historial_list = []
        if ultima_conversacion:
            historial_list = [{
                'pregunta': ultima_conversacion.pregunta,
                'respuesta': ultima_conversacion.respuesta
            }]

        contexto = buscar_contexto_relevante_rapido(mensaje)
        respuesta_precisa = responder_pregunta_admision(mensaje)
        if respuesta_precisa:
            respuesta = respuesta_precisa
        else:
            respuesta = ollama_service.consultar_con_historial(mensaje, historial_list, contexto)
        try:
            conv = Conversacion.objects.create(
                session_id=session_id,
                pregunta=mensaje,
                respuesta=respuesta
            )
        except Exception as e:
            logger.warning("No se pudo guardar conversación: %s", e)

        elapsed = time.time() - start_time
        logger.info("chat_api session=%s elapsed=%.2fs", session_id, elapsed)
        return JsonResponse({'respuesta': respuesta})
    except Exception as e:
        logger.exception("Error general en chat_api: %s", e)
        return JsonResponse({'respuesta': 'Error interno del servidor'}, status=500)

def buscar_contexto_relevante_rapido(mensaje, limite=2):
    """
    Versión ultra-rápida de búsqueda de contexto con logs
    """
    cache_key = f"contexto_{hash(mensaje)}"
    contexto_cache = cache.get(cache_key)
    if contexto_cache:
        return contexto_cache

    palabras = mensaje.lower().split()
    palabras_clave = [p for p in palabras if len(p) > 3][:3]

    if not palabras_clave:
        return ""

    contextos = []

    try:
        filtro = Q()
        for palabra in palabras_clave:
            filtro |= Q(contenido__icontains=palabra) | Q(titulo__icontains=palabra)
        query = ConocimientoUAEMEX.objects.filter(filtro).order_by('-fecha_actualizacion')[:limite]
        for conocimiento in query:
            contextos.append(conocimiento.contenido[:300])
    except Exception as e:
        logger.warning("Error en búsqueda de contexto por BD: %s", e)

    if not contextos:
        resultado_web = buscar_en_uaemex_web_rapido(mensaje)
        if resultado_web:
            contextos.append(resultado_web)

    if not contextos:
        return ""

    resultado = "\n\n".join(contextos[:limite])
    cache.set(cache_key, resultado, 60 * 5)
    return resultado

def buscar_en_uaemex_web_rapido(consulta):
    """
    Versión ultra-rápida de búsqueda web (timeout reducido) con logs
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    urls_rapidas = []
    terminos_admision = ['admis', 'examen', 'convoc', 'preinscrip', 'nuevo ingreso']
    if any(t in consulta.lower() for t in terminos_admision):
        urls_rapidas.extend(getattr(settings, 'UAEMEX_SEED_URLS', []))
        urls_rapidas.append("https://nuevoingreso.uaemex.mx/")
    urls_rapidas.extend([
        "https://www.uaemex.mx/oferta-educativa/licenciaturas",
        "https://www.uaemex.mx"
    ])
    for url in urls_rapidas:
        try:
            response = requests.get(url, headers=headers, timeout=3)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                parrafos = soup.find_all('p')[:5]
                textos = []
                for p in parrafos:
                    texto = p.get_text(strip=True)
                    if texto and len(texto) > 50:
                        palabras_consulta = consulta.lower().split()[:2]
                        if any(palabra in texto.lower() for palabra in palabras_consulta):
                            textos.append(texto[:300])
                            if len(textos) >= 2:
                                break
                if textos:
                    resultado = ' '.join(textos)
                    return resultado
        except requests.exceptions.Timeout:
            logger.info("Timeout consultando fuente %s", url)
        except Exception as e:
            logger.warning("Error consultando fuente %s: %s", url, e)
    return None


def responder_pregunta_admision(mensaje):
    mensaje_l = mensaje.lower()
    terminos = ['costo', 'cuanto cuesta', 'admis', 'examen', 'convocatoria', 'preinscrip']
    if not any(t in mensaje_l for t in terminos):
        return None

    query = ConocimientoUAEMEX.objects.filter(
        Q(titulo__icontains='admis') |
        Q(titulo__icontains='convocatoria') |
        Q(contenido__icontains='admis') |
        Q(contenido__icontains='examen') |
        Q(contenido__icontains='derechos')
    ).order_by('-fecha_actualizacion')[:30]

    mejor_monto = None
    mejor_fuente = None
    mejor_titulo = None
    for item in query:
        texto = f"{item.titulo} {item.contenido[:2000]}"
        if not any(k in texto.lower() for k in ['examen', 'admis', 'convocatoria', 'derechos']):
            continue
        montos = PATRON_MONTO.findall(texto)
        candidatos = []
        for m in montos:
            try:
                valor = int(m)
            except ValueError:
                continue
            if 150 <= valor <= 5000:
                candidatos.append(valor)
        if candidatos:
            mejor_monto = max(candidatos)
            mejor_fuente = item.fuente
            mejor_titulo = item.titulo
            break

    if mejor_monto:
        return (
            f"Con base en la información institucional más reciente disponible en el sistema, "
            f"el costo reportado del examen de admisión es de {mejor_monto} pesos mexicanos. "
            f"Fuente registrada: {mejor_titulo} ({mejor_fuente}). "
            "Te recomiendo confirmar el monto en la convocatoria vigente del ciclo que vas a presentar, "
            "porque puede cambiar por año y nivel."
        )
    costo_referencia = getattr(settings, 'UAEMEX_ADMISSION_EXAM_COST_MXN', 0)
    anio_referencia = getattr(settings, 'UAEMEX_ADMISSION_EXAM_COST_YEAR', '')
    fuente_referencia = getattr(settings, 'UAEMEX_ADMISSION_EXAM_SOURCE_URL', '')
    if costo_referencia:
        return (
            f"El monto de referencia configurado para el examen de admisión UAEMEX "
            f"({anio_referencia}) es de {costo_referencia} pesos mexicanos. "
            f"Consulta oficial: {fuente_referencia}. "
            "Te recomiendo verificar la convocatoria vigente antes de pagar, porque la cifra puede cambiar."
        )
    return (
        "Para darte un monto exacto y evitar errores, necesito validar la convocatoria vigente de admisión. "
        "Estoy actualizando las fuentes oficiales; por ahora te recomiendo revisar la convocatoria publicada "
        "en el portal de nuevo ingreso de la UAEMEX para confirmar el costo actual."
    )

def historial_api(request):
    session_id = request.session.session_key
    conversaciones = Conversacion.objects.filter(session_id=session_id)[:10]
    data = [{
        'pregunta': c.pregunta,
        'respuesta': c.respuesta[:100] + ('...' if len(c.respuesta) > 100 else ''),
        'fecha': c.fecha.strftime('%Y-%m-%d %H:%M')
    } for c in conversaciones]
    return JsonResponse({'historial': data})

def estado_api(request):
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
        cache.set(cache_key, estado, 30)
    return JsonResponse(estado)


def health_api(request):
    database_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        database_ok = False
    estado = {
        'status': 'ok' if database_ok else 'degraded',
        'database_ok': database_ok,
        'ollama_ok': ollama_service.verificar_estado_rapido(),
        'cache_ok': cache is not None,
    }
    http_code = 200 if database_ok else 503
    return JsonResponse(estado, status=http_code)
