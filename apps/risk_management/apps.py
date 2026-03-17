from django.apps import AppConfig
 
 
class RiskManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.risk_management'
 
    def ready(self):
        try:
            import apps.risk_management.signals  # noqa: F401
        except ImportError:
            pass
 