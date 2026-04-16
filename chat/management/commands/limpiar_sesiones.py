# Crea un nuevo archivo: chat/management/commands/limpiar_sesiones.py

from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Limpia sesiones corruptas o expiradas'
    
    def handle(self, *args, **options):
        # Eliminar sesiones expiradas
        expiradas = Session.objects.filter(expire_date__lt=timezone.now())
        count_exp = expiradas.count()
        expiradas.delete()
        
        # También eliminar sesiones que puedan estar corruptas
        # (sesiones con datos vacíos o inválidos)
        todas = Session.objects.all()
        corruptas = 0
        for session in todas:
            try:
                # Intentar decodificar la sesión
                session.get_decoded()
            except Exception:
                session.delete()
                corruptas += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Limpiado: {count_exp} sesiones expiradas, {corruptas} sesiones corruptas"
            )
        )