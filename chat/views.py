"""
chat/views.py

Vistas del asistente virtual UAEMex.
"""

import json
import logging
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import (
    Conversacion,
    ConocimientoUAEMEX,
    MemoriaContexto,
    MemoriaUsuario,
    Pregunta,
    ResumenConversacion,
)
from .services.memory_service import MemoriaPersistenteService
from .services.ollama_service import OllamaService

logger = logging.getLogger(__name__)
ollama_service = OllamaService()


# ---------------------------------------------------------------------------
# Vistas HTML
# ---------------------------------------------------------------------------

@ensure_csrf_cookie
def index(request):
    if not request.session.session_key:
        request.session.create()
    return render(
        request,
        "chat/index.html",
        {
            "session_id": request.session.session_key,
            "titulo": "Asistente Virtual UAEMex",
            "ollama_activo": ollama_service.verificar_estado_rapido(),
        },
    )


# ---------------------------------------------------------------------------
# API de chat principal
# ---------------------------------------------------------------------------

@require_POST
def chat_api(request):
    start_time = time.time()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"respuesta": "Solicitud inválida."}, status=400)

    mensaje = (data.get("mensaje") or "").strip()
    session_id = data.get("session_id") or request.session.session_key

    if not mensaje:
        return JsonResponse({"respuesta": "Tu mensaje está vacío."}, status=400)

    try:
        user_id = request.user.username if request.user.is_authenticated else None
        memoria_service = MemoriaPersistenteService(session_id, user_id)

        # --- Interceptor de saludos ---
        mensaje_normalizado = re.sub(r"[^\w\s]", "", mensaje.lower()).strip()
        saludos = {
            "hola", "buenas", "buenos dias", "buenas tardes",
            "buenas noches", "saludos", "que tal", "hey",
        }
        if mensaje_normalizado in saludos:
            nombre = memoria_service.memoria_usuario.nombre
            saludo = f"¡Hola, {nombre}!" if nombre else "¡Hola!"
            resp = (
                f"{saludo} Soy el Asistente Virtual Oficial de la UAEMex. "
                "¿En qué puedo ayudarte hoy?"
            )
            Conversacion.objects.create(
                session_id=session_id, pregunta=mensaje, respuesta=resp
            )
            return JsonResponse({"respuesta": resp})

        # --- Historial reciente (últimas 5 interacciones, excluyendo saludos) ---
        ultimas = list(
            Conversacion.objects.filter(session_id=session_id)
            .order_by("-fecha")[:5]
        )
        ultimas.reverse()
        historial_list = [
            {"pregunta": c.pregunta, "respuesta": c.respuesta}
            for c in ultimas
            if "¡Hola!" not in c.respuesta
        ]

        # --- Búsqueda de contexto ---
        # Si el mensaje es muy corto y hay historial, ampliar la búsqueda
        mensaje_busqueda = mensaje
        if ultimas and len(mensaje.split()) <= 4:
            ultima = ultimas[-1]
            if "¡Hola!" not in ultima.respuesta:
                mensaje_busqueda = f"{ultima.pregunta} {mensaje}"

        contexto_base = buscar_contexto_relevante_rapido(mensaje_busqueda, mensaje, limite=5)

        # --- Contexto enriquecido con memoria ---
        contexto_memoria = memoria_service.construir_prompt_con_memoria(mensaje, contexto_base)

        # Combinar: memoria del usuario + contexto de la BD
        if contexto_memoria:
            contexto_completo = f"{contexto_memoria}\n\n=== BASE DE CONOCIMIENTO ===\n{contexto_base}"
        else:
            contexto_completo = contexto_base

        # --- Llamada al LLM ---
        respuesta = ollama_service.consultar_con_historial(
            mensaje, historial_list, contexto_completo
        )

        # --- Aprendizaje y persistencia ---
        memoria_service.aprender_de_conversacion(mensaje, respuesta)
        Conversacion.objects.create(
            session_id=session_id, pregunta=mensaje, respuesta=respuesta
        )

        logger.info(
            "chat_api session=%s elapsed=%.2fs", session_id, time.time() - start_time
        )
        return JsonResponse({"respuesta": respuesta})

    except Exception as e:
        logger.exception("Error en chat_api: %s", e)
        return JsonResponse({"respuesta": "Error interno del servidor."}, status=500)


# ---------------------------------------------------------------------------
# Búsqueda de contexto por capas
# ---------------------------------------------------------------------------

def buscar_contexto_relevante_rapido(
    mensaje_busqueda: str, mensaje_original: str, limite: int = 5
) -> str:
    cache_key = f"ctx_{hash(mensaje_busqueda)}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    contextos: list[str] = []

    # ── TIER 1: frase exacta en FAQs ──────────────────────────────────────────
    frase = _normalizar(mensaje_original)
    if len(frase) > 5:
        exactas = list(Pregunta.objects.filter(pregunta__icontains=frase)[:2])
        for p in exactas:
            contextos.append(f"FAQ EXACTA — P: {p.pregunta} | R: {p.respuesta}")
        if contextos:
            resultado = "\n\n".join(contextos)
            cache.set(cache_key, resultado, 60 * 5)
            return resultado

    # ── Preparar palabras clave ────────────────────────────────────────────────
    stop_words = {
        "para", "como", "cuales", "cual", "sobre", "este", "esta", "todo", "pero",
        "nivel", "los", "las", "son", "del", "que", "una", "uno", "universidad",
        "uaemex", "uaem", "quien", "cuando", "donde", "tiene", "algun", "hacer",
        "actual", "institucion", "repite", "repetir", "anterior", "puedes",
        "decirme", "okey", "hola",
    }
    palabras_raw = _normalizar(mensaje_busqueda).split()
    palabras_clave = list(
        dict.fromkeys(
            p[:6] for p in palabras_raw if len(p) > 2 and p not in stop_words
        )
    )[:6]

    if not palabras_clave:
        palabras_clave = [p[:6] for p in palabras_raw if len(p) > 2][:6]

    if not palabras_clave:
        return ""

    # ── TIER 2: AND (todas las palabras deben aparecer) ───────────────────────
    try:
        filtro_preg = Q()
        for p in palabras_clave:
            filtro_preg &= Q(pregunta__icontains=p) | Q(respuesta__icontains=p)
        preg_and = list(Pregunta.objects.filter(filtro_preg)[:3])

        filtro_doc = Q()
        for p in palabras_clave:
            filtro_doc &= Q(contenido__icontains=p) | Q(titulo__icontains=p)
        doc_and = list(
            ConocimientoUAEMEX.objects.filter(filtro_doc).order_by("-fecha_actualizacion")[:3]
        )

        for p in preg_and:
            contextos.append(f"FAQ — P: {p.pregunta} | R: {p.respuesta}")
        for d in doc_and:
            contextos.append(f"DOC — {d.titulo}: {d.contenido[:500]}")

        if contextos:
            resultado = "\n\n".join(contextos)
            cache.set(cache_key, resultado, 60 * 5)
            return resultado
    except Exception as e:
        logger.warning("TIER 2 falló: %s", e)

    # ── TIER 3: OR (al menos una palabra) ─────────────────────────────────────
    try:
        filtro_preg = Q()
        for p in palabras_clave:
            filtro_preg |= Q(pregunta__icontains=p) | Q(respuesta__icontains=p)
        preg_or = list(Pregunta.objects.filter(filtro_preg)[:5])

        filtro_doc = Q()
        for p in palabras_clave:
            filtro_doc |= Q(contenido__icontains=p) | Q(titulo__icontains=p)
        doc_or = list(
            ConocimientoUAEMEX.objects.filter(filtro_doc).order_by("-fecha_actualizacion")[:3]
        )

        for p in preg_or:
            contextos.append(f"FAQ — P: {p.pregunta} | R: {p.respuesta}")
        for d in doc_or:
            contextos.append(f"DOC — {d.titulo}: {d.contenido[:500]}")
    except Exception as e:
        logger.warning("TIER 3 falló: %s", e)

    # ── TIER 4: búsqueda web como último recurso ───────────────────────────────
    if not contextos:
        web = buscar_en_uaemex_web_rapido(mensaje_busqueda)
        if web:
            contextos.append(web)

    resultado = "\n\n".join(contextos)
    if resultado:
        cache.set(cache_key, resultado, 60 * 5)
    return resultado


def _normalizar(texto: str) -> str:
    """Quita acentos, signos de puntuación comunes y pasa a minúsculas."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[¿?¡!.,]", "", sin_acentos).lower().strip()


def buscar_en_uaemex_web_rapido(consulta: str) -> str | None:
    """Búsqueda de respaldo en el sitio web de UAEMex."""
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = []
    if any(t in consulta.lower() for t in ["admis", "examen", "convoc", "preinscrip"]):
        urls.append("https://nuevoingreso.uaemex.mx/")
    urls += [
        "https://www.uaemex.mx/oferta-educativa/licenciaturas",
        "https://www.uaemex.mx",
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=3)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                keywords = consulta.lower().split()[:2]
                textos = []
                for p in soup.find_all("p")[:10]:
                    texto = p.get_text(strip=True)
                    if len(texto) > 50 and any(kw in texto.lower() for kw in keywords):
                        textos.append(texto[:300])
                        if len(textos) >= 2:
                            break
                if textos:
                    return " ".join(textos)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# APIs auxiliares
# ---------------------------------------------------------------------------

def historial_api(request):
    session_id = request.session.session_key
    conversaciones = list(
        Conversacion.objects.filter(session_id=session_id).order_by("-fecha")[:15]
    )
    conversaciones.reverse()
    data = [
        {
            "pregunta": c.pregunta,
            "respuesta": c.respuesta,
            "fecha": c.fecha.strftime("%Y-%m-%d %H:%M"),
        }
        for c in conversaciones
    ]
    return JsonResponse({"historial": data})


def estado_api(request):
    cache_key = "estado_ollama"
    estado = cache.get(cache_key)
    if not estado:
        estado = {
            "ollama_activo": ollama_service.verificar_estado_rapido(),
            "modelos_disponibles": len(ollama_service.listar_modelos()),
            "modelo_actual": ollama_service.model,
        }
        cache.set(cache_key, estado, 30)
    return JsonResponse(estado)


def health_api(request):
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False

    status_code = 200 if db_ok else 503
    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "db_ok": db_ok,
            "ollama_ok": ollama_service.verificar_estado_rapido(),
        },
        status=status_code,
    )


def memoria_usuario_api(request):
    """Devuelve la memoria del usuario actual."""
    session_id = request.session.session_key
    user_id = request.user.username if request.user.is_authenticated else None
    svc = MemoriaPersistenteService(session_id, user_id)
    ctx = svc.obtener_contexto_completo("")
    return JsonResponse(
        {
            "nombre": svc.memoria_usuario.nombre,
            "nivel_educativo": svc.memoria_usuario.nivel_educativo,
            "intereses": svc.memoria_usuario.intereses,
            "total_interacciones": svc.memoria_usuario.total_interacciones,
            "contexto_reciente": ctx["contexto_reciente"],
        }
    )


def reiniciar_memoria_api(request):
    """Reinicia la memoria de la sesión actual."""
    session_id = request.session.session_key
    MemoriaContexto.objects.filter(session_id=session_id).delete()
    ResumenConversacion.objects.filter(session_id=session_id).delete()
    return JsonResponse({"status": "ok", "mensaje": "Memoria reiniciada."})