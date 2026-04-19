import unittest

from examples.flask.simple_blog.blog import SimplePost, SimpleTag


class SimpleBlogCompatTests(unittest.TestCase):
    def test_simple_post_accepts_payload_mapping(self):
        post = SimplePost({"title": "Hello", "text": "World"})

        self.assertEqual(post.title, "Hello")
        self.assertEqual(post.text, "World")

    def test_tag_accepts_tag_object_and_updates_reverse_link(self):
        post = SimplePost("Hello", "World")
        tag = SimpleTag("ruby")

        post.tag(tag)

        self.assertEqual(post.tags, ["ruby"])
        self.assertEqual(tag.post_ids, [post.id])

    def test_from_dict_round_trips_float_timestamp(self):
        post = SimplePost("Hello", "World")
        post.timestamp = 1234.5

        loaded = SimplePost.from_dict({"id": post.id, **post.to_dict()})

        self.assertEqual(loaded.timestamp, 1234.5)
        self.assertEqual(loaded.title, "Hello")
        self.assertEqual(loaded.text, "World")


if __name__ == "__main__":
    unittest.main()
