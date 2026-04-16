import re
import requests
import json
import time
from django.conf import settings
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class GroqService:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.api_url = settings.GROQ_API_URL
        self.model = settings.GROQ_MODEL
        self.cache_timeout = 60 * 15
        self.timeout = 60

    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        """
        Punto de entrada principal. Construye memoria de historial y llama a consultar().
        """
        memoria = ""
        if historial:
            for h in historial:
                pregunta = h.get('pregunta', '')
                respuesta = h.get('respuesta', '')
                if pregunta and respuesta:
                    memoria += f"Usuario preguntó: {pregunta[:150]}\nAsistente respondió: {respuesta[:200]}\n---\n"

        return self.consultar(mensaje, contexto=contexto, historial_texto=memoria)

    def consultar(self, mensaje, contexto="", historial_texto="", session_id=None):
        """
        Construye el prompt completo y llama a la API de Groq.
        """
        # Si no hay contexto externo, buscar uno rápido
        if not contexto:
            contexto = self._busqueda_ultra_rapida(mensaje)

        prompt = self._construir_prompt_pro(mensaje, contexto, historial_texto)

        try:
            respuesta = self._llamar_con_reintentos(prompt)
        except Exception as e:
            print(f"❌ Error crítico tras reintentos: {e}")
            respuesta = self._get_fallback_response_pro()

        respuesta = self._limpiar_respuesta(respuesta)
        return respuesta

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
        ),
    )
    def _llamar_con_reintentos(self, prompt):
        start_time = time.time()

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el Asistente Virtual Oficial de la UAEMex. "
                    "Responde siempre en español, de forma clara, completa y útil. "
                    "Si no tienes información exacta, orienta al usuario dónde puede conseguirla."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.15,
            "max_tokens": 1200,
            "top_p": 0.9,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1,
        }

        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        elapsed = time.time() - start_time
        print(f"⏱️ Tiempo de respuesta Groq: {elapsed:.2f}s")

        if response.status_code == 200:
            try:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Error parseando respuesta: {e}")
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                detail = response.json()
                error_msg += f" — {detail.get('error', {}).get('message', '')}"
            except Exception:
                pass
            raise Exception(error_msg)

    def _construir_prompt_pro(self, mensaje, contexto, historial):
        """
        Construye el prompt enriquecido con contexto, historial y reglas de negocio UAEMex.
        """
        # Detectar preguntas de seguimiento
        palabras_seguimiento = ["eso", "esto", "ello", "ese", "esa", "por qué", "cómo es", "y eso"]
        es_seguimiento = any(p in mensaje.lower() for p in palabras_seguimiento)

        # Palabras clave propias de la UAEMex
        palabras_uaemex = {
            "seguro", "médico", "gnp", "estudiantil", "materia", "reprobar",
            "nadar", "doctor", "posgrado", "costo", "inscripción", "potrobús",
            "beca", "rectora", "zarza", "campus", "tutoría",
        }
        es_tema_uaemex = any(p in mensaje.lower() for p in palabras_uaemex)

        seccion_seguimiento = (
            "\n⚠️ NOTA: El usuario hace una pregunta de seguimiento. "
            "Responde usando el historial de conversación anterior.\n"
            if es_seguimiento
            else ""
        )

        seccion_uaemex = (
            "\n✅ NOTA: La pregunta es sobre un tema específico de UAEMex. "
            "Usa la información del contexto y los datos base.\n"
            if es_tema_uaemex
            else ""
        )

        prompt = f"""Eres el Asistente Oficial de la UAEMex. Tu misión: ser ÚTIL y PRECISO.

=== DATOS BASE UAEMex ===
- Rectora actual: Dra. Martha Patricia Zarza Delgado
- Seguro médico GNP: $702 pesos anuales (consultas, hospitalización, medicamentos)
- Potrobús: GRATUITO para estudiantes con credencial vigente
- Reprobar una materia NO es causal de expulsión; hay tutorías y regularización disponibles
- Doctorados: ofertados en múltiples facultades (Artes, Ciencias, Humanidades, Medicina, etc.)
- Instalaciones deportivas: según campus; consultar la unidad académica específica

=== CONTEXTO DE LA BASE DE CONOCIMIENTO ===
{contexto if contexto else "Sin contexto adicional disponible."}

=== HISTORIAL DE CONVERSACIÓN ===
{historial if historial else "Sin historial previo."}

=== REGLAS CRÍTICAS ===
1. Si es pregunta de seguimiento, usa el historial para responder.
2. Si hay contexto relevante, cítalo en tu respuesta.
3. NUNCA inventes datos, cifras, fechas ni nombres.
4. Si no tienes la información, di claramente dónde puede encontrarla (sitio web, número, oficina).
5. Responde siempre en español, en prosa clara, integra a la respuesta una url en donde se acceda a la informnacion requerida y sin listas innecesarias.
6. Sé conciso pero completo: máximo 2-3 párrafos.
{seccion_seguimiento}{seccion_uaemex}
PREGUNTA: {mensaje}

RESPUESTA:"""

        return prompt

    def _busqueda_ultra_rapida(self, mensaje):
        """
        Búsqueda rápida en la BD de conocimiento como respaldo cuando no hay contexto externo.
        """
        try:
            from chat.models import ConocimientoUAEMEX

            stop_words = {
                "para", "como", "cuales", "cual", "sobre", "este", "esta", "todo",
                "pero", "nivel", "los", "las", "son", "del", "que", "una", "uno",
                "universidad", "uaemex", "uaem", "quien", "cuando",
            }
            palabras = [
                p for p in mensaje.lower().split()
                if len(p) > 3 and p not in stop_words
            ][:3]

            if not palabras:
                return ""

            conocimientos = ConocimientoUAEMEX.objects.filter(
                contenido__icontains=palabras[0]
            )[:2]

            if conocimientos:
                return conocimientos[0].contenido[:500]
        except Exception:
            pass

        return ""

    def _limpiar_respuesta(self, respuesta):
        if not respuesta:
            return "Lo siento, no pude generar una respuesta. Por favor intenta de nuevo."

        respuesta = respuesta.strip()
        respuesta = respuesta.replace("\r", "").replace("\t", " ")

        # Eliminar prefijos redundantes que el modelo a veces agrega
        prefijos = ["RESPUESTA:", "Respuesta:", "ASISTENTE:", "Asistente:"]
        for prefijo in prefijos:
            if respuesta.startswith(prefijo):
                respuesta = respuesta[len(prefijo):].strip()

        # Normalizar múltiples saltos de línea
        respuesta = re.sub(r"\n{3,}", "\n\n", respuesta)

        # Eliminar caracteres fuera del plano BMP (emojis problemáticos, etc.)
        respuesta = re.sub(r"[^\u0000-\uFFFF]", "", respuesta)

        return respuesta

    def _get_fallback_response_pro(self):
        return (
            "Lo siento, tuve un problema técnico al contactar la API. "
            "Por favor intenta de nuevo en unos momentos. "
            "Si el problema persiste, puedes consultar directamente en "
            "https://www.uaemex.mx o llamar a la línea de atención universitaria."
        )

    def verificar_estado_rapido(self):
        """Verifica si la API key de Groq es válida con una llamada mínima."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
            }
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def listar_modelos(self):
        """Retorna lista de modelos disponibles en Groq (con caché de 1 hora)."""
        cache_key = "groq_models_list"
        modelos = cache.get(cache_key)
        if not modelos:
            modelos = [
                {"name": "llama-3.3-70b-versatile", "details": {"parameter_size": "70B", "status": "active"}},
                {"name": "llama-3.1-8b-instant",    "details": {"parameter_size": "8B",  "status": "active"}},
                {"name": "gemma2-9b-it",            "details": {"parameter_size": "9B",  "status": "active"}},
                {"name": "llama3-70b-8192",         "details": {"parameter_size": "70B", "status": "active"}},
                {"name": "llama3-8b-8192",          "details": {"parameter_size": "8B",  "status": "active"}},
            ]
            cache.set(cache_key, modelos, 60 * 60)
        return modelos


# Alias para compatibilidad con código existente
OllamaService = GroqService