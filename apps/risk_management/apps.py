from django.apps import AppConfig
 
 
class RiskManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'apps.risk_management'
    verbose_name       = 'Risk Management'
 
    def ready(self):
        import apps.risk_management.signals  # noqa: F401
 