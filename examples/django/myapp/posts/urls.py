"""
Port of rails/myapp/config/routes.rb → Django urls.py

Rails:   resources :posts
Django:  explicit urlpatterns matching the same REST verbs
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from django.urls import path
from . import views

urlpatterns = [
    # GET  /posts/
    path('',            views.PostListView.as_view(),   name='post_list'),
    # GET  /posts/new/   POST /posts/new/
    path('new/',        views.PostCreateView.as_view(), name='post_new'),
    # GET  /posts/<id>/
    path('<int:pk>/',   views.PostDetailView.as_view(), name='post_detail'),
    # GET  /posts/<id>/edit/   POST /posts/<id>/edit/
    path('<int:pk>/edit/',   views.PostUpdateView.as_view(), name='post_edit'),
    # POST /posts/<id>/delete/
    path('<int:pk>/delete/', views.PostDeleteView.as_view(), name='post_delete'),
]
