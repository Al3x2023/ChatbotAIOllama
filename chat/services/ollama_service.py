import re
import requests
import json
import time
import random
from django.conf import settings
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = settings.MODEL_NAME
        self.base_model = getattr(settings, 'BASE_MODEL', 'llama3.2:latest')
        self.cache_timeout = 60 * 15  # 15 minutos
        self.timeout = 60  # segundos

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        """
        Procesa el historial para enviarlo por separado y no confundir a la IA.
        """
        historial_texto = ""
        if historial and len(historial) > 0:
            for h in historial:
                # Tomamos un resumen corto de la charla pasada
                historial_texto += f"Usuario: {h['pregunta']}\nAsistente: {h['respuesta'][:150]}\n"
        
        # Llamamos a consultar pasando el historial como un bloque independiente
        return self.consultar(mensaje, contexto=contexto, historial_texto=historial_texto)

    def consultar(self, mensaje, contexto="", historial_texto="", session_id=None):
        """
        Envía una consulta a Llama 3.2 con reintentos y control de calidad.
        """
        # --- CACHÉ DESACTIVADO TEMPORALMENTE ---
        # cache_key = f"ollama_response_{hash(mensaje + contexto)}"
        # cached_response = cache.get(cache_key)
        # if cached_response:
        #     print(f"⚡ Respuesta desde caché para: {mensaje[:30]}...")
        #     return cached_response
        # ----------------------------------------

        # Búsqueda rápida en BD si no hay contexto
        if not contexto:
            contexto = self._busqueda_ultra_rapida(mensaje)

        # Construimos el prompt separando el historial de la información oficial
        prompt = self._construir_prompt_pro(mensaje, contexto, historial_texto)
        options = self._get_options_pro(mensaje)

        try:
            respuesta = self._llamar_con_reintentos(prompt, options)
        except Exception as e:
            print(f"❌ Error crítico tras reintentos: {e}")
            respuesta = self._get_fallback_response_pro()

        # Verificar si la respuesta está truncada
        if respuesta and (respuesta.endswith(':') or respuesta.endswith(':\n') or not respuesta[-1] in '.!?'):
            print("⚠️ Posible respuesta truncada, intentando completar...")
            prompt_completar = f"{prompt}\n{respuesta}\nContinúa la respuesta de forma natural:"
            try:
                respuesta_completa = self._llamar_con_reintentos(prompt_completar, options)
                if respuesta_completa:
                    respuesta = respuesta + " " + respuesta_completa
            except:
                pass

        # Limpiar emojis para MySQL y dar formato
        respuesta = self._limpiar_respuesta(respuesta)

        # --- CACHÉ DESACTIVADO TEMPORALMENTE ---
        # if len(respuesta) > 10:
        #     cache.set(cache_key, respuesta, self.cache_timeout)
        # ----------------------------------------

        return respuesta

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
    )
    def _llamar_con_reintentos(self, prompt, options):
        """Llama a Ollama con reintentos automáticos."""
        start_time = time.time()
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": options
            },
            timeout=self.timeout,
            headers={'Connection': 'close'}
        )
        elapsed_time = time.time() - start_time
        print(f"⏱️ Tiempo de respuesta: {elapsed_time:.2f}s")

        if response.status_code == 200:
            try:
                result = response.json()
                return result.get('response', '')
            except json.JSONDecodeError:
                print("Error decodificando JSON, respuesta raw:", response.text[:200])
                raise Exception("Respuesta no JSON")
        else:
            raise Exception(f"HTTP {response.status_code}")

    def _busqueda_ultra_rapida(self, mensaje):
        """Búsqueda rápida en BD (solo primera palabra clave)."""
        from chat.models import ConocimientoUAEMEX
        palabras = mensaje.lower().split()
        
        # Ignorar las mismas palabras clave que en views.py
        stop_words = {'para', 'como', 'cuales', 'cual', 'sobre', 'este', 'esta', 'todo', 'pero', 'nivel', 'los', 'las', 'son', 'del', 'que', 'una', 'uno', 'universidad', 'uaemex', 'uaem', 'quien', 'quién', 'cuando', 'cuándo'}
        palabras_filtradas = [p for p in palabras if len(p) > 3 and p not in stop_words][:3]
        
        if not palabras_filtradas:
            return ""
        try:
            conocimientos = ConocimientoUAEMEX.objects.filter(
                contenido__icontains=palabras_filtradas[0]
            )[:2]
            if conocimientos:
                return conocimientos[0].contenido[:500]
        except Exception as e:
            print(f"Error en búsqueda ultra rápida: {e}")
        return ""

    def _construir_prompt_pro(self, mensaje, contexto, historial):
        """Prompt maestro con soporte multilingüe y candado de exclusividad UAEMex."""
        prompt = f"""Eres el Asistente Virtual Oficial Exclusivo de la Universidad Autónoma del Estado de México (UAEMex).
Tu deber es responder basándote en la información oficial y en el historial de la plática.

--- BASE DE CONOCIMIENTO OFICIAL ---
{contexto[:3000] if contexto else "No se encontraron documentos oficiales para esta pregunta."}

--- HISTORIAL DE LA CONVERSACIÓN ---
{historial if historial else "Sin historial previo."}

--- REGLAS ESTRICTAS E INQUEBRANTABLES ---
1. EXCLUSIVIDAD UAEMEX: Eres un asistente estrictamente universitario. Si la pregunta del usuario NO tiene relación con la UAEMex, educación, trámites o vida universitaria, DEBES NEGARTE a responder. Di amablemente: "Lo siento, soy un asistente exclusivo de la UAEMex y solo puedo responder dudas sobre la universidad."
2. MULTILINGÜE: Detecta el idioma de la 'PREGUNTA ACTUAL DEL USUARIO'. Debes responder exactamente en ese mismo idioma (ej. si te hablan en inglés, responde en inglés; si en francés, en francés), traduciendo la información de la Base de Conocimiento si es necesario.
3. DIRECTO AL GRANO: PROHIBIDO SALUDAR o presentarte. Responde DIRECTAMENTE a la pregunta.
4. EXCEPCIÓN DE MEMORIA: Si el usuario te pide REPETIR, ACLARAR o RESUMIR algo de la plática anterior, usa el HISTORIAL para contestarle.
5. NO INVENTES: Si es una pregunta válida sobre la UAEMex pero la BASE DE CONOCIMIENTO dice "No se encontraron documentos...", responde: "No cuento con esa información específica en mi sistema en este momento. ¿Podrías darme más detalles o contactar a tu espacio académico?".

PREGUNTA ACTUAL DEL USUARIO:
{mensaje}

RESPUESTA DIRECTA:"""
        return prompt

    def _get_options_pro(self, mensaje):
        """Opciones ajustadas para precisión."""
        return {
            "temperature": 0.2,          # Súper analítico para que obedezca las reglas
            "top_p": 0.9,
            "max_tokens": 1500,          
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.2,
            "num_predict": 1500,         
            "stop": ["\n\nPREGUNTA ACTUAL DEL USUARIO:", "Usuario:"]
        }

    def _limpiar_respuesta(self, respuesta):
        if not respuesta:
            return "Lo siento, no pude generar una respuesta."
        
        # Eliminar saltos de línea excesivos
        respuesta = respuesta.replace('\r', '').replace('\t', ' ')
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        respuesta_limpia = '\n'.join(lineas)

        # Filtro Anti-Emojis para MySQL
        respuesta_limpia = re.sub(r'[^\x00-\xFFFF]', '', respuesta_limpia)

        return respuesta_limpia

    def _get_fallback_response_pro(self):
        return "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo en unos momentos."

    def verificar_estado_rapido(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    def listar_modelos(self):
        cache_key = 'ollama_models_list'
        modelos = cache.get(cache_key)
        if not modelos:
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    modelos = response.json().get('models', [])
                    cache.set(cache_key, modelos, 60 * 60)
            except:
                modelos = []
        return modelos