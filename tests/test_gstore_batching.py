import unittest
from unittest import mock

import gemstone_py.gstore as mod


class GStoreBatchingTests(unittest.TestCase):
    def test_read_file_uses_batched_pair_fetch(self):
        session = mock.Mock()
        file_map = type("FakeMap", (), {"_oop": 9876})()

        with mock.patch.object(mod, "_ensure_root", return_value=mock.sentinel.root) as ensure_root:
            with mock.patch.object(mod, "_ensure_file", return_value=file_map) as ensure_file:
                with mock.patch.object(
                    mod,
                    "_fetch_mapping_string_pairs",
                    return_value=[
                        ("alpha", '{"name": "Tariq", "count": 2}'),
                        ("beta", '["a", "b"]'),
                        ("gamma", "plain-text"),
                    ],
                ) as fetch_pairs:
                    result = mod._read_file(session, "sample.db")

        self.assertEqual(
            result,
            {
                "alpha": {"name": "Tariq", "count": 2},
                "beta": ["a", "b"],
                "gamma": "plain-text",
            },
        )
        ensure_root.assert_called_once_with(session)
        ensure_file.assert_called_once_with(mock.sentinel.root, "sample.db")
        fetch_pairs.assert_called_once_with(session, 9876)


if __name__ == "__main__":
    unittest.main()
