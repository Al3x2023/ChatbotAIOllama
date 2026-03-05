import subprocess
import tempfile
import os
from django.conf import settings
from chat.models import ConocimientoUAEMEX
from .ollama_service import OllamaService

class ModelUpdater:
    def __init__(self):
        self.ollama = OllamaService()
        self.model_name = settings.MODEL_NAME
        self.base_model = settings.BASE_MODEL
    
    def generar_conocimiento_combinado(self):
        """
        Combina todo el conocimiento de la BD para crear el contexto
        """
        conocimientos = ConocimientoUAEMEX.objects.all()[:50]  # Limitar cantidad
        
        if not conocimientos:
            return "Información de la UAEMEX no disponible."
        
        texto_combinado = []
        
        for conocimiento in conocimientos:
            texto_combinado.append(f"--- {conocimiento.titulo.upper()} ---")
            texto_combinado.append(conocimiento.contenido)
            texto_combinado.append("")  # Línea en blanco
        
        return "\n".join(texto_combinado)
    
    def crear_modelfile(self):
        """
        Crea el archivo Modelfile para Ollama
        """
        conocimiento = self.generar_conocimiento_combinado()
        
        modelfile_content = f"""FROM {self.base_model}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER max_tokens 2048

SYSTEM Eres un asistente virtual oficial de la Universidad Autónoma del Estado de México (UAEMEX).

INFORMACIÓN INSTITUCIONAL:
{conocimiento}

DIRECTRICES:
1. Siempre responde en español, de forma clara y profesional
2. Usa la información institucional proporcionada cuando sea relevante
3. Si te preguntan algo que no está en la base de conocimiento, dilo honestamente
4. Mantén un tono amable y servicial, representando los valores de la UAEMEX
5. Proporciona información precisa y actualizada sobre la universidad
6. Si necesitas más información, sugiere consultar las fuentes oficiales

Tu objetivo es ayudar a estudiantes, profesores y público en general con información sobre la UAEMEX.
"""
        
        return modelfile_content
    
    def actualizar_modelo(self):
        """
        Actualiza el modelo en Ollama
        """
        print("🔄 Iniciando actualización del modelo...")
        
        try:
            # Crear archivo temporal para Modelfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(self.crear_modelfile())
                modelfile_path = f.name
            
            print(f"📝 Modelfile creado temporalmente")
            
            # Ejecutar comando ollama create
            comando = [
                "ollama", "create",
                self.model_name,
                "-f", modelfile_path
            ]
            
            print(f"⚙️ Ejecutando: {' '.join(comando)}")
            
            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutos máximo
            )
            
            # Eliminar archivo temporal
            os.unlink(modelfile_path)
            
            if resultado.returncode == 0:
                print(f"✅ Modelo {self.model_name} actualizado correctamente")
                return {
                    'success': True,
                    'message': f"Modelo {self.model_name} actualizado",
                    'output': resultado.stdout
                }
            else:
                print(f"❌ Error: {resultado.stderr}")
                return {
                    'success': False,
                    'message': "Error actualizando modelo",
                    'error': resultado.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'message': "Timeout: La actualización tomó demasiado tiempo"
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error inesperado: {str(e)}"
            }
    
    def verificar_modelo(self):
        """
        Verifica si el modelo personalizado existe
        """
        modelos = self.ollama.listar_modelos()
        
        for modelo in modelos:
            if modelo.get('name') == self.model_name:
                return True
        
        return False