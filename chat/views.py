import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
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

        historial = Conversacion.objects.filter(session_id=session_id)[:5]
        historial_list = [{'pregunta': h.pregunta, 'respuesta': h.respuesta} for h in historial]

        contexto = buscar_contexto_relevante(mensaje)
        respuesta = ollama_service.consultar_con_historial(mensaje, historial_list, contexto)

        Conversacion.objects.create(
            session_id=session_id,
            pregunta=mensaje,
            respuesta=respuesta
        )

        return JsonResponse({'respuesta': respuesta})
    except Exception as e:
        print(f"Error en chat_api: {e}")
        return JsonResponse({'respuesta': 'Error interno del servidor'}, status=500)

def buscar_contexto_relevante(mensaje, limite=3):
    print(f"🔍 Buscando contexto para: {mensaje}")
    palabras = mensaje.lower().split()
    contextos = []

    # Buscar en base de datos
    for palabra in palabras[:5]:
        if len(palabra) < 4:
            continue
        conocimientos = ConocimientoUAEMEX.objects.filter(contenido__icontains=palabra)[:limite]
        for conocimiento in conocimientos:
            if conocimiento.contenido not in contextos:
                print(f"  ✅ Encontrado en BD: {conocimiento.titulo}")
                contextos.append(conocimiento.contenido[:500])

    # Si no hay resultados, buscar en internet en tiempo real
    if not contextos:
        print("🌐 Buscando en internet en tiempo real...")
        resultados_web = buscar_en_uaemex_web(mensaje)
        if resultados_web:
            contextos.extend(resultados_web)
            print(f"  ✅ Encontrado en web: {len(resultados_web)} resultados")

    if not contextos:
        print("  ❌ No se encontró información")
        return ""

    return "\n\n".join(contextos[:limite])

def buscar_en_uaemex_web(consulta):
    """
    Busca en el sitio web de UAEMEX en tiempo real.
    IMPORTANTE: Actualiza las rutas según la estructura actual del sitio.
    """
    resultados = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # Mapeo de palabras clave a rutas (sin extensión .html)
    # ⚠️ REEMPLAZA ESTAS RUTAS CON LAS QUE ENCUENTRES EN EL SITIO ACTUAL
    secciones = [
       ('carreras', '/oferta-educativa/licenciaturas'),
    ('licenciatura', '/oferta-educativa/licenciaturas'),
    ('facultades', '/oferta-educativa/centros-universitarios-y-unidades-academicas-profesionales-uaemex'),
    ('inscripcion', '/vida-universitaria/alumnos/control-escolar'),
    ('becas', '/vida-universitaria/alumnos/becas'),
    ('contacto', '/contacto'),
    ('historia', '/mi-universidad/bienvenido-a-la-uaemex/historia'),
    ('mision', '/mi-universidad/bienvenido-a-la-uaemex/mision-y-vision'),
    ('convocatorias', '/oferta-educativa/aspirantes/convocatorias-ingreso-2026'),
    ]

    # Elegir la URL según la consulta
    url_a_visitar = None
    for palabra_clave, url in secciones:
        if palabra_clave in consulta.lower():
            url_a_visitar = f"https://www.uaemex.mx{url}"
            break

    if not url_a_visitar:
        url_a_visitar = "https://www.uaemex.mx"

    try:
        print(f"  🌐 Visitando: {url_a_visitar}")
        response = requests.get(url_a_visitar, headers=headers, timeout=15)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Eliminar elementos no deseados
            for elemento in soup(['script', 'style', 'nav', 'footer', 'header']):
                elemento.decompose()

            # Intentar extraer contenido principal
            selectores = [
                'main', 'article', '.content', '#content',
                '.main-content', '.contenido-principal',
                'div[class*="oferta"]', 'div[class*="licenciatura"]',
                '.entry-content', '#primary'
            ]
            contenido_principal = None
            for selector in selectores:
                contenido_principal = soup.select_one(selector)
                if contenido_principal:
                    break

            if contenido_principal:
                parrafos = contenido_principal.find_all('p')
                for p in parrafos[:5]:
                    texto = p.get_text(strip=True)
                    if texto and len(texto) > 100:
                        resultados.append(texto[:500])
            else:
                parrafos = soup.find_all('p')
                for p in parrafos[:10]:
                    texto = p.get_text(strip=True)
                    if texto and len(texto) > 100:
                        resultados.append(texto[:500])

            # Si aún no hay resultados, tomar texto completo
            if not resultados:
                textos = soup.stripped_strings
                texto_completo = ' '.join(list(textos)[:500])
                if len(texto_completo) > 200:
                    resultados.append(texto_completo[:500])

    except Exception as e:
        print(f"  ❌ Error en búsqueda web: {e}")

    return resultados

def historial_api(request):
    session_id = request.session.session_key
    conversaciones = Conversacion.objects.filter(session_id=session_id)[:20]
    data = [{
        'pregunta': c.pregunta,
        'respuesta': c.respuesta,
        'fecha': c.fecha.strftime('%Y-%m-%d %H:%M')
    } for c in conversaciones]
    return JsonResponse({'historial': data})

def estado_api(request):
    ollama_ok = ollama_service.verificar_estado_rapido()
    modelos = ollama_service.listar_modelos()
    return JsonResponse({
        'ollama_activo': ollama_ok,
        'modelos_disponibles': modelos,
        'modelo_actual': ollama_service.model
    })