import requests
import json
import time
import random
from django.conf import settings
from django.core.cache import cache

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = 'llama3.2:latest'  # Modelo personalizado
        self.base_model = settings.BASE_MODEL
        self.cache_timeout = 60 * 15  # 15 minutos
        self.timeout = 1000  # Timeout reducido para respuestas más rápidas

    def consultar(self, mensaje, contexto="", session_id=None):
        """
        Envía una consulta a Llama 3.2 optimizada para velocidad.
        """
        # Cache más agresivo
        cache_key = f"ollama_response_{hash(mensaje + contexto)}"
        cached_response = cache.get(cache_key)
        if cached_response:
            print(f"⚡ Respuesta desde caché para: {mensaje[:30]}...")
            return cached_response

        # Si no hay contexto, intentar búsqueda ultra-rápida
        if not contexto:
            contexto = self._busqueda_ultra_rapida(mensaje)

        prompt = self._construir_prompt_rapido(mensaje, contexto)
        options = self._get_options_rapidas(mensaje)

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
                timeout=self.timeout,  # Timeout más bajo
                headers={'Connection': 'close'}
            )

            elapsed_time = time.time() - start_time
            print(f"⏱️ Tiempo de respuesta: {elapsed_time:.2f}s")

            if response.status_code == 200:
                try:
                    result = response.json()
                    respuesta = result.get('response', '')
                except json.JSONDecodeError:
                    print(f"Error decodificando JSON")
                    respuesta = "Lo siento, hubo un problema al procesar la respuesta."

                respuesta = self._limpiar_respuesta(respuesta)

                # Guardar en caché incluso respuestas más rápidas
                if len(respuesta) > 10 and elapsed_time > 1:
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
            return self._get_fallback_response_rapida()

    def _busqueda_ultra_rapida(self, mensaje):
        """
        Búsqueda ultra-rápida de palabras clave en la BD
        """
        from chat.models import ConocimientoUAEMEX
        
        palabras = mensaje.lower().split()
        palabras_filtradas = [p for p in palabras if len(p) > 3][:3]
        
        if not palabras_filtradas:
            return ""
        
        # Búsqueda simple y rápida (solo un query)
        conocimientos = ConocimientoUAEMEX.objects.filter(
            contenido__icontains=palabras_filtradas[0]
        )[:2]
        
        if conocimientos:
            return conocimientos[0].contenido[:500]
        return ""

    def _construir_prompt_rapido(self, mensaje, contexto):
        """
        Prompt más corto y directo para respuestas rápidas
        """
        prompt = f"""Eres un asistente de la UAEMEX. Responde rápido y preciso.

CONTEXTO: {contexto[:500] if contexto else 'Sin información específica'}

REGLAS:
- Respuesta breve (máx 3 oraciones)
- Si no sabes, di: "Consulta la página oficial"

PREGUNTA: {mensaje}

RESPUESTA:"""
        return prompt

    def _get_options_rapidas(self, mensaje):
        """
        Opciones optimizadas para velocidad máxima
        """
        palabras = mensaje.split()
        
        # Configuración ultra-rápida para cualquier pregunta
        return {
            "temperature": 0.3,  # Más determinista = más rápido
            "top_p": 0.85,
            "max_tokens": 100 if len(palabras) < 5 else 200,
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.2,
            "num_ctx": 1024,  # Contexto reducido
            "num_predict": 100,  # Límite de predicción
            "stop": ["\n\n", "PREGUNTA:", "Usuario:"]  # Parar temprano
        }

    def _limpiar_respuesta(self, respuesta):
        """
        Limpieza rápida de la respuesta
        """
        if not respuesta:
            return "Lo siento, no pude generar una respuesta."

        # Limpieza simple y rápida
        respuesta = respuesta.replace('\r', '').replace('\t', ' ')
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        
        if not lineas:
            return respuesta[:200]
        
        return ' '.join(lineas)[:500]

    def _get_fallback_response_rapida(self):
        """
        Respuestas de respaldo ultra-rápidas
        """
        respuestas = [
            "Lo siento, no pude procesar tu solicitud.",
            "Error de conexión. Intenta de nuevo.",
            "No tengo esa información ahora.",
            "¿Podrías ser más específico?"
        ]
        return random.choice(respuestas)

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        """
        Versión con contexto de conversación anterior (optimizada)
        """
        contexto_historial = ""
        if historial and len(historial) > 0:
            # Solo la última interacción para velocidad
            ultima = historial[-1]
            contexto_historial = f"Anterior: {ultima['pregunta']} -> {ultima['respuesta'][:100]}"

        contexto_completo = f"{contexto}\n{contexto_historial}" if contexto else contexto_historial
        return self.consultar(mensaje, contexto_completo)

    def verificar_estado_rapido(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=1)
            return response.status_code == 200
        except:
            return False

    def listar_modelos(self):
        cache_key = 'ollama_models_list'
        modelos = cache.get(cache_key)
        if not modelos:
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=2)
                if response.status_code == 200:
                    modelos = response.json().get('models', [])
                    cache.set(cache_key, modelos, 60 * 60)
            except:
                modelos = []
        return modelos