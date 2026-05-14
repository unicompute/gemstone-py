import unittest
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import mock
from uuid import UUID

import gemstone_py as gemstone
from gemstone_py.converters import (
    ValueConverter,
    ValueConverterRegistry,
    dataclass_to_dict,
    date_as_iso_string_converter,
    datetime_converter,
    decimal_as_string_converter,
    scalar_value_converter_registry,
    uuid_as_string_converter,
)
from gemstone_py.oop import Oop
from gemstone_py.persistent_root import _to_oop


class ValueConverterTests(unittest.TestCase):
    def test_registry_converts_datetime_to_oop_marker(self):
        session = mock.Mock()
        session.eval_oop.return_value = 9001
        registry = scalar_value_converter_registry()

        converted = registry.to_oop(
            session,
            datetime(2026, 5, 14, 12, 30, tzinfo=timezone.utc),
        )

        self.assertIsInstance(converted, Oop)
        self.assertEqual(converted.oop, 9001)
        self.assertIn("DateAndTime posixSeconds:", session.eval_oop.call_args.args[0])

    def test_registry_extends_copies_and_converts_batches(self):
        converter = ValueConverter[int](
            name="int_string",
            python_type=int,
            exact_type=True,
            to_oop_fn=lambda session, value: session.new_string(str(value)),
            from_oop_fn=lambda session, oop: int(session.fetch_string(oop)),
        )
        registry = ValueConverterRegistry()
        registry.extend([converter])

        copied = registry.copy()
        copied.register(decimal_as_string_converter())

        self.assertEqual(registry.names(), ("int_string",))
        self.assertEqual(copied.names(), ("int_string", "decimal_string"))

        session = mock.Mock()
        session.new_string.side_effect = [101, 202]
        self.assertEqual(registry.to_oops(session, [1, 2]), [Oop(101), Oop(202)])
        session.new_string.assert_has_calls([mock.call("1"), mock.call("2")])

        session.fetch_string.side_effect = ["10", "20"]
        self.assertEqual(registry.from_oops("int_string", session, [101, Oop(202)]), [10, 20])

    def test_date_converter_uses_exact_date_type(self):
        converter = date_as_iso_string_converter()

        self.assertTrue(converter.matches(date(2026, 5, 14)))
        self.assertFalse(converter.matches(datetime(2026, 5, 14, tzinfo=timezone.utc)))

    def test_string_backed_converters_round_trip(self):
        session = mock.Mock()

        date_converter = date_as_iso_string_converter()
        session.new_string.return_value = 101
        self.assertEqual(date_converter.to_oop(session, date(2026, 5, 14)), 101)
        session.fetch_string.return_value = "2026-05-14"
        self.assertEqual(date_converter.from_oop(session, 101), date(2026, 5, 14))

        decimal_converter = decimal_as_string_converter()
        session.new_string.return_value = 202
        self.assertEqual(decimal_converter.to_oop(session, Decimal("12.34")), 202)
        session.fetch_string.return_value = "12.34"
        self.assertEqual(decimal_converter.from_oop(session, 202), Decimal("12.34"))

        uuid_converter = uuid_as_string_converter()
        value = UUID("12345678-1234-5678-1234-567812345678")
        session.new_string.return_value = 303
        self.assertEqual(uuid_converter.to_oop(session, value), 303)
        session.fetch_string.return_value = str(value)
        self.assertEqual(uuid_converter.from_oop(session, 303), value)

    def test_datetime_converter_round_trip_hooks_are_explicit(self):
        converter = datetime_converter()
        session = mock.Mock()
        session.eval_oop.return_value = 404

        oop = converter.to_oop(session, datetime(2026, 5, 14, tzinfo=timezone.utc))

        self.assertEqual(oop, 404)
        self.assertIn("datetime", converter.name)

    def test_dataclass_to_dict(self):
        @dataclass
        class Booking:
            customer: str
            amount: Decimal

        payload = dataclass_to_dict(Booking("Alice", Decimal("10.50")), recurse=False)

        self.assertEqual(payload, {"customer": "Alice", "amount": Decimal("10.50")})

    def test_dataclass_to_dict_rejects_non_instances(self):
        @dataclass
        class Booking:
            customer: str

        with self.assertRaises(TypeError):
            dataclass_to_dict(Booking)

        with self.assertRaises(TypeError):
            dataclass_to_dict({"customer": "Alice"})

    def test_oop_marker_survives_existing_value_conversion_paths(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        self.assertEqual(session._python_value_to_oop(Oop(1234)), 1234)
        self.assertEqual(_to_oop(mock.Mock(), Oop(5678)), 5678)


if __name__ == "__main__":
    unittest.main()
