"""
Post model for the Django example app.

Rails: class Post < ActiveRecord::Base  (backed by SQLite)
Django: class Post(models.Model)        (backed by SQLite via Django ORM)

Django's ORM is the direct equivalent: models.Model with automatic
migrations, the same CRUD pattern, and JSON responses via DRF or
JsonResponse.
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from django.db import models


class Post(models.Model):
    name    = models.CharField(max_length=255)
    title   = models.CharField(max_length=255)
    content = models.TextField()

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.title
