"""
Django form for Post — replaces Rails scaffold form helpers.
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from django import forms
from .models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model  = Post
        fields = ['name', 'title', 'content']
