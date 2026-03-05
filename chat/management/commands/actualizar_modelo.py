from django.core.management.base import BaseCommand
from chat.services.model_updater import ModelUpdater

class Command(BaseCommand):
    help = 'Actualiza el modelo de Ollama con la información de UAEMEX'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando actualización del modelo...'))
        
        updater = ModelUpdater()
        resultado = updater.actualizar_modelo()
        
        if resultado['success']:
            self.stdout.write(self.style.SUCCESS(f"✅ {resultado['message']}"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ {resultado['message']}"))
            if 'error' in resultado:
                self.stdout.write(self.style.ERROR(resultado['error']))