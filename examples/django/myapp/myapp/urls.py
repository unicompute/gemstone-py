"""
Project URLs for the Rails myapp port.
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView


urlpatterns = [
    path('', TemplateView.as_view(template_name='home/index.html'), name='home'),
    path('posts/', include('posts.urls')),
    path('admin/', admin.site.urls),
]
