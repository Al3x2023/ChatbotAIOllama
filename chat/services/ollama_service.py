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
        # 🧠 HACK DE SEGURIDAD: Quitamos la palabra "Usuario" y "Pregunta"
        # Lo convertimos en una lista de hechos fríos para no activar filtros PII.
        memoria = ""
        if historial and len(historial) > 0:
            for h in historial:
                memoria += f"- Dato reciente compartido: {h['respuesta'][:200]}\n"
        
        return self.consultar(mensaje, contexto=contexto, historial_texto=memoria)

    def consultar(self, mensaje, contexto="", historial_texto="", session_id=None):
        if not contexto:
            contexto = self._busqueda_ultra_rapida(mensaje)

        prompt = self._construir_prompt_pro(mensaje, contexto, historial_texto)
        options = self._get_options_pro(mensaje)

        try:
            respuesta = self._llamar_con_reintentos(prompt, options)
        except Exception as e:
            print(f"❌ Error crítico tras reintentos: {e}")
            respuesta = self._get_fallback_response_pro()

        if respuesta and (respuesta.endswith(':') or respuesta.endswith(':\n') or not respuesta[-1] in '.!?'):
            prompt_completar = f"{prompt}\n{respuesta}\nContinúa:"
            try:
                respuesta_completa = self._llamar_con_reintentos(prompt_completar, options)
                if respuesta_completa:
                    respuesta = respuesta + " " + respuesta_completa
            except:
                pass

        respuesta = self._limpiar_respuesta(respuesta)
        return respuesta

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
    )
    def _llamar_con_reintentos(self, prompt, options):
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
                raise Exception("Respuesta no JSON")
        else:
            raise Exception(f"HTTP {response.status_code}")

    def _busqueda_ultra_rapida(self, mensaje):
        from chat.models import ConocimientoUAEMEX
        palabras = mensaje.lower().split()
        stop_words = {'para', 'como', 'cuales', 'cual', 'sobre', 'este', 'esta', 'todo', 'pero', 'nivel', 'los', 'las', 'son', 'del', 'que', 'una', 'uno', 'universidad', 'uaemex', 'uaem', 'quien', 'quién', 'cuando', 'cuándo'}
        palabras_filtradas = [p for p in palabras if len(p) > 3 and p not in stop_words][:3]
        
        if not palabras_filtradas: return ""
        try:
            conocimientos = ConocimientoUAEMEX.objects.filter(contenido__icontains=palabras_filtradas[0])[:2]
            if conocimientos: return conocimientos[0].contenido[:500]
        except: pass
        return ""

    def _construir_prompt_pro(self, mensaje, contexto, historial):
        palabras_ingles = {'what', 'when', 'where', 'who', 'why', 'how', 'is', 'the', 'can', 'you', 'please', 'tell'}
        mensaje_words = set(mensaje.lower().replace('?', '').replace('¿', '').split())
        
        if mensaje_words.intersection(palabras_ingles):
            regla_idioma = "RESPOND IN ENGLISH. If you don't know the answer, say: 'I do not have that information in my database.'"
            etiqueta_final = "ANSWER:"
        else:
            regla_idioma = "RESPONDE EN ESPAÑOL. Si no sabes la respuesta, di: 'No tengo esta información en mi sistema.'"
            etiqueta_final = "RESPUESTA:"

        prompt = f"""Eres el Asistente Oficial de la UAEMex.
AVISO DE SEGURIDAD CRÍTICO: Toda la información que manejas es PÚBLICA e institucional. NO manejas datos personales de la persona que escribe.

=== DATOS INSTITUCIONALES ===
{contexto[:3000] if contexto else "Sin datos oficiales."}

=== MEMORIA RECIENTE (Tus respuestas anteriores) ===
{historial if historial else "Sin memoria."}

=== INSTRUCCIONES ===
1. MEMORIA DE AUTORIDADES: Si te piden "repetir su nombre" o "quién es", busca en la MEMORIA RECIENTE el nombre del Rector, Director o autoridad mencionada y dalo. Es información pública, TIENES PERMITIDO compartirla.
2. NO INVENTES DATOS. Usa solo los DATOS INSTITUCIONALES o la MEMORIA RECIENTE.
3. EXCLUSIVIDAD ABSOLUTA: Tienes ESTRICTAMENTE PROHIBIDO hablar de temas que no sean de la UAEMex (nada de recetas, deportes, ni tareas). Si te preguntan algo ajeno, responde ÚNICAMENTE: "Lo siento, soy un asistente exclusivo de la UAEMex." y termina tu respuesta de inmediato, sin ofrecer más ayuda.
4. IDIOMA: {regla_idioma}

PREGUNTA:
{mensaje}

{etiqueta_final}"""
        return prompt

    def _get_options_pro(self, mensaje):
        return {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 1500,          
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.2,
            "num_predict": 1500,         
            "stop": ["\n\nPREGUNTA:", "Dato reciente compartido:"]
        }

    def _limpiar_respuesta(self, respuesta):
        if not respuesta: return "Lo siento, no pude generar una respuesta."
        respuesta = respuesta.replace('\r', '').replace('\t', ' ')
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        respuesta_limpia = '\n'.join(lineas)
        respuesta_limpia = re.sub(r'[^\x00-\xFFFF]', '', respuesta_limpia)
        return respuesta_limpia

    def _get_fallback_response_pro(self):
        return "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo en unos momentos."

    def verificar_estado_rapido(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except: return False

    def listar_modelos(self):
        cache_key = 'ollama_models_list'
        modelos = cache.get(cache_key)
        if not modelos:
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    modelos = response.json().get('models', [])
                    cache.set(cache_key, modelos, 60 * 60)
            except: modelos = []
        return modelos