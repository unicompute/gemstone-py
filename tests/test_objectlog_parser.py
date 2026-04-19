import unittest
from unittest import mock

from gemstone_py.objectlog import _decode_log_field, _fetch_log_entries


class ObjectLogParserTests(unittest.TestCase):
    def test_decode_log_field_restores_escaped_delimiters(self):
        encoded = r"alpha\pbravo\ncharlie\rdelta\\echo"

        decoded = _decode_log_field(encoded)

        self.assertEqual(decoded, "alpha|bravo\ncharlie\rdelta\\echo")

    def test_fetch_log_entries_decodes_escaped_fields(self):
        session = mock.Mock()
        session.eval.return_value = (
            r"4|hello\pworld|obj\\repr\nline|123|2026-04-19\r12:00|1|'tag\pvalue'" r"\q"
        )

        entries = _fetch_log_entries(session)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].priority, 4)
        self.assertEqual(entries[0].label, "hello|world")
        self.assertEqual(entries[0].object_repr, "obj\\repr\nline")
        self.assertEqual(entries[0].pid, 123)
        self.assertEqual(entries[0].timestamp, "2026-04-19\r12:00")
        self.assertTrue(entries[0].tagged)
        self.assertEqual(entries[0].tag, "tag|value")


if __name__ == "__main__":
    unittest.main()
