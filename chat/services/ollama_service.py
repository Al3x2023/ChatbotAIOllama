import requests
import json
import time
import random
from django.conf import settings
from django.core.cache import cache

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = 'llama3.2:latest'
        self.base_model = settings.BASE_MODEL
        # Cache para respuestas frecuentes (15 minutos)
        self.cache_timeout = 60 * 15
        
    def consultar(self, mensaje, contexto="", session_id=None):
        """
        Envía una consulta optimizada a Llama 3.2
        """
        # Normalizar mensaje para cache
        cache_key = f"ollama_response_{hash(mensaje + contexto)}"
        
        # Verificar cache primero
        cached_response = cache.get(cache_key)
        if cached_response:
            print(f"⚡ Respuesta desde caché para: {mensaje[:30]}...")
            return cached_response
        
        # Construir prompt optimizado
        prompt = self._construir_prompt_optimizado(mensaje, contexto)
        
        # Configurar opciones optimizadas
        options = self._get_optimized_options(mensaje)
        
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
                headers={'Connection': 'close'}  # Liberar conexión rápido
            )
            
            elapsed_time = time.time() - start_time
            print(f"⏱️ Tiempo de respuesta: {elapsed_time:.2f}s")
            
            if response.status_code == 200:
                result = response.json()
                respuesta = result.get('response', '')
                
                # Limpiar y validar respuesta
                respuesta = self._limpiar_respuesta(respuesta)
                
                # Guardar en caché si es una respuesta válida
                if len(respuesta) > 10 and elapsed_time > 2:
                    cache.set(cache_key, respuesta, self.cache_timeout)
                
                return respuesta
            else:
                return f"⚠️ Error en el servicio (código {response.status_code})"
                
        except requests.exceptions.Timeout:
            return "⏱️ La consulta está tomando demasiado tiempo. Por favor, simplifica tu pregunta."
        except requests.exceptions.ConnectionError:
            return "🔌 No puedo conectar con el servicio de IA. ¿Está funcionando Ollama?"
        except Exception as e:
            print(f"Error en OllamaService: {e}")
            return self._get_fallback_response(mensaje)
    
    def _construir_prompt_optimizado(self, mensaje, contexto):
        """
        Prompt más eficiente y directo para respuestas rápidas
        """
        # Limitar contexto a lo esencial
        contexto_limitado = contexto[:1000] if contexto else ""
        
        prompt = f"""Eres un asistente de la UAEMEX. Responde SOLO si tienes información precisa.

CONTEXTO DISPONIBLE:
{contexto_limitado if contexto_limitado else "Sin información específica"}

REGLAS ESTRICTAS:
1. Si NO sabes la respuesta, di: "No tengo información específica sobre eso. Consulta la página oficial de la UAEMEX."
2. Responde en UNA sola oración cuando sea posible
3. Máximo 3 oraciones por respuesta
4. Basa tu respuesta EXCLUSIVAMENTE en el contexto proporcionado
5. No inventes datos, fechas o información no verificada

PREGUNTA: {mensaje}

RESPUESTA (precisa y concisa):"""
        
        return prompt
    
    def _get_optimized_options(self, mensaje):
        """
        Opciones dinámicas según la complejidad de la pregunta
        """
        # Preguntas cortas = respuestas rápidas
        if len(mensaje.split()) < 5:
            return {
                "temperature": 0.3,  # Más determinista
                "top_p": 0.8,
                "max_tokens": 100,   # Respuesta corta
                "repeat_penalty": 1.2
            }
        # Preguntas complejas = más contexto
        else:
            return {
                "temperature": 0.5,   # Balance
                "top_p": 0.85,
                "max_tokens": 250,    # Respuesta media
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.3  # Evita repeticiones
            }
    
    def _limpiar_respuesta(self, respuesta):
        """
        Limpia y valida la respuesta
        """
        if not respuesta:
            return "No pude generar una respuesta válida."
        
        # Eliminar espacios extras y líneas en blanco
        lineas = [linea.strip() for linea in respuesta.split('\n') if linea.strip()]
        respuesta_limpia = ' '.join(lineas)
        
        # Verificar que no esté inventando
        palabras_invento = ['según mi conocimiento', 'creo que', 'probablemente', 'tal vez']
        for palabra in palabras_invento:
            if palabra in respuesta_limpia.lower():
                respuesta_limpia = "No tengo información confirmada sobre eso. " + respuesta_limpia
        
        return respuesta_limpia
    
    def _get_fallback_response(self, mensaje):
        """
        Respuestas de respaldo cuando hay error
        """
        respuestas_fallback = [
            "Lo siento, no pude procesar tu consulta. ¿Podrías reformularla?",
            "Hubo un error en la conexión. Por favor, intenta de nuevo.",
            "No tengo acceso a esa información en este momento.",
            "¿Podrías ser más específico en tu pregunta?"
        ]
        return random.choice(respuestas_fallback)
    
    def consultar_con_historial(self, mensaje, historial=None, contexto=""):
        """
        Versión con contexto de conversación anterior
        """
        contexto_historial = ""
        if historial:
            # Tomar solo las últimas 3 interacciones
            ultimas = historial[-3:]
            contexto_historial = "Historial reciente:\n" + "\n".join([
                f"Usuario: {h['pregunta']}\nAsistente: {h['respuesta']}"
                for h in ultimas
            ])
        
        # Combinar contexto de BD con historial
        contexto_completo = f"{contexto}\n\n{contexto_historial}" if contexto else contexto_historial
        
        return self.consultar(mensaje, contexto_completo)
    
    def verificar_estado_rapido(self):
        """
        Verificación rápida de estado (con timeout bajo)
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def listar_modelos(self):
        """
        Lista los modelos disponibles (con cache)
        """
        cache_key = 'ollama_models_list'
        modelos = cache.get(cache_key)
        
        if not modelos:
            try:
                response = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    modelos = response.json().get('models', [])
                    cache.set(cache_key, modelos, 60 * 60)  # Cache por 1 hora
            except:
                modelos = []
        
        return modelos