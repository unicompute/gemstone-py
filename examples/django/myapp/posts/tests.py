"""
Functional tests mirroring the original Rails scaffold tests.
"""

from django.test import TestCase
from django.urls import reverse

from .models import Post


class PostsViewTests(TestCase):
    def setUp(self):
        self.post = Post.objects.create(
            name='Alice',
            title='First post',
            content='Hello from the Django scaffold port.',
        )

    def test_index(self):
        response = self.client.get(reverse('post_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.title)

    def test_new(self):
        response = self.client.get(reverse('post_new'))
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        response = self.client.post(
            reverse('post_new'),
            {'name': 'Bob', 'title': 'Created', 'content': 'Created via POST'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 2)

    def test_show(self):
        response = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.post.content)

    def test_edit(self):
        response = self.client.get(reverse('post_edit', args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update(self):
        response = self.client.post(
            reverse('post_edit', args=[self.post.pk]),
            {'name': 'Alice', 'title': 'Updated', 'content': 'Updated body'},
        )
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'Updated')

    def test_destroy(self):
        response = self.client.post(reverse('post_delete', args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 0)
