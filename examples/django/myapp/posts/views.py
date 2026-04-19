"""
Port of rails/myapp/app/controllers/posts_controller.rb → Django views

Rails PostsController actions → Django view functions:
  index   → PostListView (GET  /posts/)
  show    → post_detail  (GET  /posts/<id>/)
  new     → post_new     (GET  /posts/new/)
  create  → post_new     (POST /posts/new/)
  edit    → post_edit    (GET  /posts/<id>/edit/)
  update  → post_edit    (POST /posts/<id>/edit/)
  destroy → post_delete  (POST /posts/<id>/delete/)

Rails respond_to format.json → Django JsonResponse
"""

PORTING_STATUS = "application_adaptation"
RUNTIME_REQUIREMENT = "Works on plain GemStone images; uses Flask or Django"

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views import View
from django.contrib import messages

from .models import Post
from .forms import PostForm


def _wants_json(request) -> bool:
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept


class PostListView(View):
    """GET /posts/ — index"""

    def get(self, request):
        posts = Post.objects.all()
        if _wants_json(request):
            data = list(posts.values('id', 'name', 'title', 'content'))
            return JsonResponse(data, safe=False)
        return render(request, 'posts/index.html', {'posts': posts})


class PostDetailView(View):
    """GET /posts/<id>/ — show"""

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        if _wants_json(request):
            return JsonResponse({'id': post.pk, 'name': post.name,
                                  'title': post.title, 'content': post.content})
        return render(request, 'posts/show.html', {'post': post})


class PostCreateView(View):
    """GET /posts/new/ — new form; POST /posts/new/ — create"""

    def get(self, request):
        form = PostForm()
        if _wants_json(request):
            return JsonResponse({})
        return render(request, 'posts/form.html', {'form': form, 'action': 'New'})

    def post(self, request):
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save()
            if _wants_json(request):
                return JsonResponse(
                    {'id': post.pk, 'name': post.name,
                     'title': post.title, 'content': post.content},
                    status=201
                )
            messages.success(request, 'Post was successfully created.')
            return redirect('post_detail', pk=post.pk)
        if _wants_json(request):
            return JsonResponse({'errors': form.errors}, status=422)
        return render(request, 'posts/form.html', {'form': form, 'action': 'New'})


class PostUpdateView(View):
    """GET /posts/<id>/edit/ — edit form; POST — update"""

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        form = PostForm(instance=post)
        return render(request, 'posts/form.html',
                       {'form': form, 'post': post, 'action': 'Edit'})

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            if _wants_json(request):
                return JsonResponse({}, status=200)
            messages.success(request, 'Post was successfully updated.')
            return redirect('post_detail', pk=post.pk)
        if _wants_json(request):
            return JsonResponse({'errors': form.errors}, status=422)
        return render(request, 'posts/form.html',
                       {'form': form, 'post': post, 'action': 'Edit'})


class PostDeleteView(View):
    """POST /posts/<id>/delete/ — destroy"""

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        post.delete()
        if _wants_json(request):
            return JsonResponse({}, status=204)
        return redirect('post_list')
