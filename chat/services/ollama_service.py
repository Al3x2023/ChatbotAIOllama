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
        self.model = settings.MODEL_NAME  # 'uaemex-llama3.2:latest' o 'llama3.2:latest'
        self.base_model = settings.BASE_MODEL
        self.cache_timeout = 60 * 15  # 15 minutos
        self.timeout = 60  # segundos

    def consultar(self, mensaje, contexto="", session_id=None):
        """
        Envía una consulta a Llama 3.2 con reintentos y control de calidad.
        """
        cache_key = f"ollama_response_{hash(mensaje + contexto)}"
        cached_response = cache.get(cache_key)
        if cached_response:
            print(f"⚡ Respuesta desde caché para: {mensaje[:30]}...")
            return cached_response

        # Búsqueda rápida en BD si no hay contexto
        if not contexto:
            contexto = self._busqueda_ultra_rapida(mensaje)

        prompt = self._construir_prompt_pro(mensaje, contexto)
        options = self._get_options_pro(mensaje)

        try:
            respuesta = self._llamar_con_reintentos(prompt, options)
        except Exception as e:
            print(f"❌ Error crítico tras reintentos: {e}")
            respuesta = self._get_fallback_response_pro()

        # Verificar si la respuesta está truncada (termina con ':' o sin puntuación final)
        if respuesta and (respuesta.endswith(':') or respuesta.endswith(':\n') or not respuesta[-1] in '.!?'):
            print("⚠️ Posible respuesta truncada, intentando completar...")
            # Pedir al modelo que complete la idea
            prompt_completar = f"{prompt}\n{respuesta}\nContinúa la respuesta de forma natural:"
            try:
                respuesta_completa = self._llamar_con_reintentos(prompt_completar, options)
                if respuesta_completa:
                    respuesta = respuesta + " " + respuesta_completa
            except:
                pass

        respuesta = self._limpiar_respuesta(respuesta)

        if len(respuesta) > 10:
            cache.set(cache_key, respuesta, self.cache_timeout)

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
        palabras_filtradas = [p for p in palabras if len(p) > 3][:3]
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

    def _construir_prompt_pro(self, mensaje, contexto):
        """Prompt con personalidad UAEMEX, sin restricciones de longitud."""
        prompt = f"""Eres la UAEMEX personificada: una universidad pública mexicana, orgullosa de tu historia y tu comunidad. Hablas en primera persona, con calidez, cercanía y profesionalismo. Tu objetivo es ayudar a estudiantes, aspirantes y público en general.

CONTEXTO (información que tienes disponible):
{contexto[:1000] if contexto else 'Confía en tu conocimiento general sobre la UAEMEX y la educación superior en México.'}

PREGUNTA DEL USUARIO:
{mensaje}

RESPUESTA (como si fueras la UAEMEX hablando directamente):"""
        return prompt

    def _get_options_pro(self, mensaje):
        """Opciones generosas para respuestas completas."""
        return {
            "temperature": 0.7,          # Creatividad equilibrada
            "top_p": 0.9,
            "max_tokens": 500,            # Suficiente para respuestas largas
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.2,
            "num_ctx": 2048,
            "num_predict": 500,
            "stop": ["\n\nPREGUNTA:", "Usuario:"]
        }

    def _limpiar_respuesta(self, respuesta):
        if not respuesta:
            return "Lo siento, no pude generar una respuesta."
        respuesta = respuesta.replace('\r', '').replace('\t', ' ')
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        if not lineas:
            return respuesta[:500]
        return ' '.join(lineas)[:1000]  # Límite más alto

    def _get_fallback_response_pro(self):
        return "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo en unos momentos."

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        contexto_historial = ""
        if historial and len(historial) > 0:
            ultima = historial[-1]
            contexto_historial = f"Conversación anterior: Usuario preguntó '{ultima['pregunta']}' y se respondió '{ultima['respuesta'][:100]}'."
        contexto_completo = f"{contexto}\n{contexto_historial}" if contexto else contexto_historial
        return self.consultar(mensaje, contexto_completo)

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