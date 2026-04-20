import unittest
from unittest import mock

from gemstone_py.concurrency import Repository, list_instances


class InstanceListingTests(unittest.TestCase):
    def test_repository_list_instances_wraps_results_when_requested(self):
        session = mock.Mock()
        session.resolve.return_value = 999
        session.eval_oop.return_value = 444
        repo = Repository(session)

        with (
            mock.patch(
                "gemstone_py.concurrency.fetch_mapping_string_oop_lists",
                return_value=[("RcCounter", [101, 102]), ("RcQueue", [303])],
            ),
            mock.patch(
                "gemstone_py.concurrency._wrap_oop",
                side_effect=lambda _s, oop: f"wrapped:{oop}",
            ) as wrap_oop,
        ):
            result = repo.list_instances(["RcCounter", "RcQueue"], wrap=True)

        self.assertEqual(
            result,
            {
                "RcCounter": ["wrapped:101", "wrapped:102"],
                "RcQueue": ["wrapped:303"],
            },
        )
        self.assertEqual(wrap_oop.call_args_list, [
            mock.call(session, 101),
            mock.call(session, 102),
            mock.call(session, 303),
        ])

    def test_repository_list_instances_preserves_raw_oops_by_default(self):
        session = mock.Mock()
        session.resolve.return_value = 999
        session.eval_oop.return_value = 444
        repo = Repository(session)

        with mock.patch(
            "gemstone_py.concurrency.fetch_mapping_string_oop_lists",
            return_value=[("RcCounter", [101, 102])],
        ):
            result = repo.list_instances(["RcCounter"])

        self.assertEqual(result, {"RcCounter": [101, 102]})

    def test_list_instances_wraps_results_when_requested(self):
        session = mock.Mock()
        session.eval_oop.return_value = 777

        with (
            mock.patch(
                "gemstone_py.concurrency.fetch_collection_oops",
                return_value=[101, 102],
            ),
            mock.patch(
                "gemstone_py.concurrency._wrap_oop",
                side_effect=lambda _s, oop: f"wrapped:{oop}",
            ) as wrap_oop,
        ):
            result = list_instances(session, "RcCounter", wrap=True)

        self.assertEqual(result, ["wrapped:101", "wrapped:102"])
        self.assertEqual(wrap_oop.call_args_list, [
            mock.call(session, 101),
            mock.call(session, 102),
        ])

    def test_list_instances_preserves_raw_oops_by_default(self):
        session = mock.Mock()
        session.eval_oop.return_value = 777

        with mock.patch(
            "gemstone_py.concurrency.fetch_collection_oops",
            return_value=[101, 102],
        ):
            result = list_instances(session, "RcCounter")

        self.assertEqual(result, [101, 102])


if __name__ == "__main__":
    unittest.main()
