import subprocess
import tempfile
import os
import re
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
        Combina todo el conocimiento de la BD para crear el contexto,
        limitando la cantidad y limpiando caracteres problemáticos.
        """
        conocimientos = ConocimientoUAEMEX.objects.all()[:5]

        if not conocimientos:
            return "Información de la UAEMEX no disponible."

        texto_combinado = []

        for conocimiento in conocimientos:
            # Limpiar el contenido: eliminar caracteres de control y espacios excesivos
            contenido_limpio = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', conocimiento.contenido)
            contenido_limpio = ' '.join(contenido_limpio.split())
            titulo_limpio = conocimiento.titulo.upper()

            texto_combinado.append(f"--- {titulo_limpio} ---")
            texto_combinado.append(contenido_limpio)
            texto_combinado.append("")  # Línea en blanco

        return "\n".join(texto_combinado)

    def crear_modelfile(self):
        """
        Crea el contenido del archivo Modelfile para Ollama,
        con el bloque SYSTEM correctamente delimitado por triples comillas.
        """
        conocimiento = self.generar_conocimiento_combinado()

        modelfile_content = f"""FROM {self.base_model}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_predict 2048

SYSTEM \"\"\"
Eres un asistente virtual oficial de la Universidad Autónoma del Estado de México (UAEMEX).

INFORMACIÓN INSTITUCIONAL:
{conocimiento}

DIRECTRICES:
1. Siempre responde en español, de forma clara y profesional.
2. Usa la información institucional proporcionada cuando sea relevante.
3. Si te preguntan algo que no está en la base de conocimiento, dilo honestamente.
4. Mantén un tono amable y servicial, representando los valores de la UAEMEX.
5. Proporciona información precisa y actualizada sobre la universidad.
6. Si necesitas más información, sugiere consultar las fuentes oficiales.

Tu objetivo es ayudar a estudiantes, profesores y público en general con información sobre la UAEMEX.
\"\"\"
"""
        return modelfile_content

    def actualizar_modelo(self):
        """
        Actualiza el modelo en Ollama creando un nuevo modelo personalizado.
        """
        print("🔄 Iniciando actualización del modelo...")

        try:
            # Crear archivo temporal con codificación UTF-8
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(self.crear_modelfile())
                modelfile_path = f.name

            print(f"📝 Modelfile creado temporalmente en: {modelfile_path}")

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
                timeout=300,
                encoding='utf-8'
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
        Verifica si el modelo personalizado existe en Ollama.
        """
        modelos = self.ollama.listar_modelos()
        for modelo in modelos:
            if modelo.get('name') == self.model_name:
                return True
        return False