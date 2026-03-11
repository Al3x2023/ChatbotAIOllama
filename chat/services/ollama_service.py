import requests
import json
import time
import random
from django.conf import settings
from django.core.cache import cache

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = 'uaemex-llama3.2:latest'  # o settings.MODEL_NAME si ya apunta a ese
        self.base_model = settings.BASE_MODEL
        self.cache_timeout = 60 * 15  # 15 minutos

    def consultar(self, mensaje, contexto="", session_id=None):
        """
        Envía una consulta a Llama 3.2 con un equilibrio entre precisión y creatividad.
        """
        cache_key = f"ollama_response_{hash(mensaje + contexto)}"
        cached_response = cache.get(cache_key)
        if cached_response:
            print(f"⚡ Respuesta desde caché para: {mensaje[:30]}...")
            return cached_response

        prompt = self._construir_prompt(mensaje, contexto)
        options = self._get_options(mensaje)

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": options
                },
                timeout=60,
                headers={'Connection': 'close'}
            )

            elapsed_time = time.time() - start_time
            print(f"⏱️ Tiempo de respuesta: {elapsed_time:.2f}s")

            if response.status_code == 200:
                try:
                    result = response.json()
                    respuesta = result.get('response', '')
                except json.JSONDecodeError:
                    print(f"Error decodificando JSON, respuesta raw: {response.text[:200]}")
                    respuesta = "Lo siento, hubo un problema al procesar la respuesta."

                respuesta = self._limpiar_respuesta(respuesta)

                if len(respuesta) > 10 and elapsed_time > 2:
                    cache.set(cache_key, respuesta, self.cache_timeout)

                return respuesta
            else:
                return f"⚠️ Error en el servicio (código {response.status_code})"

        except requests.exceptions.Timeout:
            return "⏱️ La consulta está tomando demasiado tiempo. Por favor, intenta de nuevo más tarde."
        except requests.exceptions.ConnectionError:
            return "🔌 No puedo conectar con el servicio de IA. ¿Está Ollama funcionando?"
        except Exception as e:
            print(f"Error en OllamaService: {e}")
            return self._get_fallback_response()

    def _construir_prompt(self, mensaje, contexto):
        """
        Construye un prompt que permite al modelo usar su conocimiento general
        pero priorizando el contexto proporcionado.
        """
        limite_contexto = 2000  # Aumentamos el límite
        contexto_limitado = contexto[:limite_contexto] if contexto else ""

        prompt = f"""Eres un asistente virtual amable y servicial de la Universidad Autónoma del Estado de México (UAEMEX). Tu objetivo es ayudar a estudiantes, profesores y público en general.

CONTEXTO RELEVANTE (si está disponible, úsalo para responder):
{contexto_limitado if contexto_limitado else "No hay información específica proporcionada."}

INSTRUCCIONES:
- Responde siempre en español, de forma clara y educada.
- Si el contexto proporcionado contiene información útil, úsala para dar una respuesta precisa.
- Si no hay contexto o es insuficiente, puedes usar tu conocimiento general sobre universidades y trámites educativos, pero sé honesto y menciona que la información puede no ser específica de la UAEMEX.
- Si no sabes la respuesta, sugiere consultar la página oficial de la UAEMEX o reformular la pregunta.
- No inventes datos oficiales como fechas exactas, promedios o requisitos si no están en el contexto.
- Puedes dar ejemplos generales si es útil.

PREGUNTA DEL USUARIO:
{mensaje}

RESPUESTA:"""
        return prompt

    def _get_options(self, mensaje):
        """
        Configura opciones dinámicas según la complejidad de la pregunta.
        """
        palabras = mensaje.split()
        if len(palabras) < 5:
            # Pregunta corta: respuesta más directa
            return {
                "temperature": 0.5,
                "top_p": 0.9,
                "max_tokens": 200,
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.2
            }
        else:
            # Pregunta más elaborada: permitir más creatividad
            return {
                "temperature": 0.7,
                "top_p": 0.95,
                "max_tokens": 400,
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.3
            }

    def _limpiar_respuesta(self, respuesta):
        """
        Limpieza básica de la respuesta sin censurar frases comunes.
        """
        if not respuesta:
            return "Lo siento, no pude generar una respuesta."

        # Eliminar espacios extra y saltos de línea excesivos
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        respuesta_limpia = ' '.join(lineas)

        # Eliminar posibles caracteres de control (opcional)
        respuesta_limpia = respuesta_limpia.replace('\r', '').replace('\t', ' ')

        return respuesta_limpia

    def _get_fallback_response(self):
        """
        Respuestas de respaldo cuando hay error.
        """
        respuestas = [
            "Lo siento, en este momento no puedo procesar tu solicitud. Por favor, intenta más tarde.",
            "Hubo un error de conexión con el servicio de IA. Intenta de nuevo en unos momentos.",
            "No estoy seguro de cómo responder a eso ahora mismo. ¿Podrías reformular tu pregunta?",
            "Lo siento, no pude obtener una respuesta. Asegúrate de que el servicio de Ollama esté funcionando."
        ]
        return random.choice(respuestas)

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        """
        Versión con contexto de conversación anterior.
        """
        contexto_historial = ""
        if historial and len(historial) > 0:
            # Tomar las últimas 3 interacciones
            ultimas = historial[-3:]
            contexto_historial = "Historial de la conversación:\n" + "\n".join([
                f"Usuario: {h['pregunta']}\nAsistente: {h['respuesta']}"
                for h in ultimas
            ])

        # Combinar contexto de BD, historial y el nuevo mensaje
        contexto_completo = f"{contexto}\n\n{contexto_historial}" if contexto else contexto_historial
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