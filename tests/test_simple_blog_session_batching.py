import unittest
from unittest import mock

from examples.flask.simple_blog.blog import SimplePost, SimpleTag


class SimpleBlogSessionBatchingTests(unittest.TestCase):
    def test_persistent_new_passes_session_to_save(self):
        marker = object()

        def fake_save(self, session=None):
            self._saved_session = session
            return self

        with mock.patch.object(SimplePost, "save", autospec=True, side_effect=fake_save):
            post = SimplePost.persistent_new({"title": "Hello", "text": "World"}, session=marker)

        self.assertEqual(post.title, "Hello")
        self.assertIs(post._saved_session, marker)

    def test_stage_passes_session_to_save(self):
        marker = object()
        tag = SimpleTag("ruby")

        def fake_save(self, session=None):
            self._saved_session = session
            return self

        with mock.patch.object(SimpleTag, "save", autospec=True, side_effect=fake_save):
            result = SimpleTag.stage(tag, session=marker)

        self.assertIs(result, tag)
        self.assertIs(tag._saved_session, marker)

    def test_find_by_name_reuses_session(self):
        marker = object()
        ruby = SimpleTag("ruby")
        python = SimpleTag("python")

        with mock.patch.object(SimpleTag, "all", return_value=[python, ruby]) as all_tags:
            found = SimpleTag.find_by_name("ruby", session=marker)

        all_tags.assert_called_once_with(session=marker)
        self.assertIs(found, ruby)


if __name__ == "__main__":
    unittest.main()
