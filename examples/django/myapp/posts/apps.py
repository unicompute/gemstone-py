from django.apps import AppConfig

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"


class PostsConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'posts'
