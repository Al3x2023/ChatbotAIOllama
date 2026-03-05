import requests
import json
from django.conf import settings

class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = settings.MODEL_NAME
        self.base_model = settings.BASE_MODEL
    
    def consultar(self, mensaje, contexto=""):
        """
        Envía una consulta a Llama 3.2 y obtiene respuesta
        """
        # Construir el prompt con contexto
        prompt = self._construir_prompt(mensaje, contexto)
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "max_tokens": 500
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '')
            else:
                return f"Error: {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            return "❌ No puedo conectar con Ollama. ¿Está corriendo el servicio?"
        except Exception as e:
            return f"❌ Error inesperado: {str(e)}"
    
    def _construir_prompt(self, mensaje, contexto):
        """
        Construye el prompt con el contexto de UAEMEX
        """
        prompt = f"""Eres un asistente virtual experto de la Universidad Autónoma del Estado de México (UAEMEX).

INFORMACIÓN DE CONTEXTO:
{contexto if contexto else "No hay información específica disponible."}

REGLAS:
- Responde siempre en español
- Sé amable y profesional
- Si no sabes algo, dilo honestamente
- Usa información oficial de UAEMEX cuando esté disponible
- Mantén un tono servicial y educativo

PREGUNTA DEL USUARIO: {mensaje}

RESPUESTA (como asistente UAEMEX):"""
        
        return prompt
    
    def verificar_estado(self):
        """
        Verifica si Ollama está funcionando
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except:
            return False
    
    def listar_modelos(self):
        """
        Lista los modelos disponibles en Ollama
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                return response.json().get('models', [])
            return []
        except:
            return []