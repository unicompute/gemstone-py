import contextlib
import unittest
from typing import Protocol
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.gsquery import GSCollection


class BookingRecord(Protocol):
    status: str
    age: int


class GSCollectionHelpersTests(unittest.TestCase):
    def test_collection_member_oops_reads_via_as_array(self):
        session = mock.Mock()
        session.perform_oop.side_effect = [500, 101, 102]
        session.perform_value.return_value = 2

        result = GSCollection._collection_member_oops(session, 123)

        self.assertEqual(result, [101, 102])
        self.assertEqual(session.perform_oop.call_args_list, [
            mock.call(123, 'asArray'),
            mock.call(500, 'at:', gemstone._python_to_smallint(1)),
            mock.call(500, 'at:', gemstone._python_to_smallint(2)),
        ])
        session.perform_value.assert_called_once_with(500, 'size')

    def test_path_array_oop_builds_array_without_eval(self):
        session = mock.Mock()
        session.resolve.return_value = 700
        session.new_string.side_effect = [901, 902]
        session.perform_oop.side_effect = [800, 800, 800]

        result = GSCollection._path_array_oop(session, '@age.@zip')

        self.assertEqual(result, 800)
        session.resolve.assert_called_once_with('Array')
        self.assertEqual(session.perform_oop.call_args_list, [
            mock.call(700, 'new:', gemstone._python_to_smallint(2)),
            mock.call(800, 'at:put:', gemstone._python_to_smallint(1), 901),
            mock.call(800, 'at:put:', gemstone._python_to_smallint(2), 902),
        ])

    def test_keys_from_dict_oop_reads_keys_via_batched_eval(self):
        session = mock.Mock()
        session.eval.return_value = "People\nJobs\\pArchive\n"

        result = GSCollection._keys_from_dict_oop(session, 123)

        self.assertEqual(result, ['People', 'Jobs|Archive'])
        session.eval.assert_called_once()

    def test_dict_from_oop_materializes_values_via_batched_oops(self):
        session = mock.Mock()
        session.eval.return_value = "People|101\nJobs\\pArchive|202\n"

        with mock.patch(
            "gemstone_py.gsquery._from_oop",
            side_effect=["Alice", {"active": True}],
        ) as from_oop:
            result = GSCollection._dict_from_oop(session, 123)

        self.assertEqual(
            result,
            {"People": "Alice", "Jobs|Archive": {"active": True}},
        )
        self.assertEqual(
            from_oop.call_args_list,
            [mock.call(session, 101), mock.call(session, 202)],
        )
        session.eval.assert_called_once()

    def test_plain_value_prefers_items_for_mapping_like_values(self):
        mapping = mock.Mock()
        mapping.items.return_value = [("alpha", 1), ("beta", 2)]

        result = GSCollection._plain_value(mapping)

        self.assertEqual(result, {"alpha": 1, "beta": 2})
        mapping.items.assert_called_once_with()
        mapping.keys.assert_not_called()

    def test_records_from_collection_oop_decodes_json_lines(self):
        session = mock.Mock()
        session.eval.return_value = (
            '{"@name":"Alice","@age":30}\n'
            '{"@name":"Bob","@tags":["staff","remote"]}\n'
        )

        result = GSCollection._records_from_collection_oop(session, 4321)

        self.assertEqual(
            result,
            [
                {'@name': 'Alice', '@age': 30},
                {'@name': 'Bob', '@tags': ['staff', 'remote']},
            ],
        )
        session.eval.assert_called_once()


class GSCollectionQueryTests(unittest.TestCase):
    def test_query_where_lambda_maps_attribute_comparison_to_ivar_path(self):
        col = GSCollection('Bookings')

        query = col.query(BookingRecord).where(lambda booking: booking.status == "booked")

        with mock.patch.object(
            col,
            'search_iter',
            return_value=iter([{'@status': 'booked'}]),
        ) as search_iter:
            result = query.all()

        self.assertEqual(result[0].status, 'booked')
        self.assertEqual(result[0]['@status'], 'booked')
        search_iter.assert_called_once_with('@status', 'eql', 'booked', chunk_size=256, session=None)

    def test_typed_query_materializes_nested_attribute_records(self):
        col = GSCollection('Bookings')

        query = col.query(BookingRecord)

        with mock.patch.object(
            col,
            'iter',
            return_value=iter([{'@status': 'booked', '@address': {'@zip': '90210'}}]),
        ):
            result = query.all()

        self.assertEqual(result[0].status, 'booked')
        self.assertEqual(result[0].address.zip, '90210')
        self.assertEqual(result[0].to_dict(), {'@status': 'booked', '@address': {'@zip': '90210'}})

    def test_query_where_lambda_supports_nested_paths_and_range_operators(self):
        col = GSCollection('Bookings')

        query = col.query().where(lambda booking: booking.address.zip == "90210").where(
            lambda booking: booking.age >= 21
        )

        with mock.patch.object(
            col,
            'search_iter',
            return_value=iter([
                {'@address': {'@zip': '90210'}, '@age': 20},
                {'@address': {'@zip': '90210'}, '@age': 30},
            ]),
        ) as search_iter:
            result = query.all()

        self.assertEqual(result, [{'@address': {'@zip': '90210'}, '@age': 30}])
        search_iter.assert_called_once_with(
            '@address.@zip',
            'eql',
            '90210',
            chunk_size=256,
            session=None,
        )

    def test_query_where_rejects_non_comparison_lambdas(self):
        col = GSCollection('Bookings')

        with self.assertRaisesRegex(TypeError, "field comparison"):
            col.query().where(lambda booking: booking.status)

    def test_query_where_string_form_still_requires_all_parts(self):
        col = GSCollection('Bookings')

        with self.assertRaisesRegex(TypeError, "ivar_path, op, and value"):
            col.query().where('@status')  # type: ignore[call-overload]

    def test_search_oops_uses_indexed_perform_path(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.new_symbol.return_value = 444
        session.perform_oop.return_value = 555

        with mock.patch.object(GSCollection, '_ensure_root', autospec=True):
            with mock.patch.object(
                GSCollection,
                '_set_oop',
                autospec=True,
                return_value=111,
            ):
                with mock.patch.object(
                    GSCollection,
                    '_path_array_oop',
                    autospec=True,
                    return_value=222,
                ):
                    with mock.patch.object(
                        GSCollection,
                        '_collection_member_oops',
                        autospec=True,
                        return_value=[7, 8],
                    ) as member_oops:
                        with mock.patch('gemstone_py.gsquery._to_oop', return_value=333):
                            result = col._search_oops(session, '@age', 'lt', 25)

        self.assertEqual(result, [7, 8])
        session.perform_oop.assert_called_once_with(111, 'search:comparing:with:', 222, 444, 333)
        session.new_symbol.assert_called_once_with('<')
        session.eval_oop.assert_not_called()
        member_oops.assert_called_once_with(session, 555)

    def test_search_oops_falls_back_to_select_eval_oop(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.new_symbol.return_value = 444
        session.perform_oop.side_effect = RuntimeError('missing index')
        session.eval_oop.return_value = 666

        with mock.patch.object(GSCollection, '_ensure_root', autospec=True):
            with mock.patch.object(
                GSCollection,
                '_set_oop',
                autospec=True,
                return_value=111,
            ):
                with mock.patch.object(
                    GSCollection,
                    '_path_array_oop',
                    autospec=True,
                    return_value=222,
                ):
                    with mock.patch.object(
                        GSCollection,
                        '_collection_member_oops',
                        autospec=True,
                        return_value=[9],
                    ) as member_oops:
                        with mock.patch('gemstone_py.gsquery._to_oop', return_value=333):
                            result = col._search_oops(session, '@age', 'lt', 25)

        self.assertEqual(result, [9])
        session.eval_oop.assert_called_once()
        self.assertIn("select: [:e |", session.eval_oop.call_args.args[0])
        member_oops.assert_called_once_with(session, 666)

    def test_search_materializes_records_from_result_collection(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.perform_oop.return_value = 222
        session.perform_value.return_value = 1

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(
                GSCollection,
                '_search_result_oop',
                autospec=True,
                return_value=777,
            ) as search_result:
                with mock.patch.object(
                    GSCollection,
                    '_records_from_array_range_oop',
                    autospec=True,
                    return_value=[{'@name': 'Bob', '@age': 24}],
                ) as records:
                    result = col.search('@age', 'lt', 25)

        self.assertEqual(result, [{'@name': 'Bob', '@age': 24}])
        search_result.assert_called_once_with(col, session, '@age', 'lt', 25)
        session.perform_oop.assert_called_once_with(777, 'asArray')
        session.perform_value.assert_called_once_with(222, 'size')
        records.assert_called_once_with(session, 222, 1, 1)

    def test_iter_reads_records_in_chunks(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.perform_oop.return_value = 222
        session.perform_value.return_value = 3

        with mock.patch.object(
            GSCollection,
            '_set_oop',
            autospec=True,
            return_value=111,
        ) as set_oop:
            with mock.patch.object(
                GSCollection,
                '_records_from_array_range_oop',
                autospec=True,
                side_effect=[
                    [{'@name': 'Alice'}, {'@name': 'Bob'}],
                    [{'@name': 'Carol'}],
                ],
            ) as chunk:
                result = list(col.iter(chunk_size=2, session=session))

        self.assertEqual(result, [{'@name': 'Alice'}, {'@name': 'Bob'}, {'@name': 'Carol'}])
        set_oop.assert_called_once_with(col, session)
        session.perform_oop.assert_called_once_with(111, 'asArray')
        session.perform_value.assert_called_once_with(222, 'size')
        self.assertEqual(
            chunk.call_args_list,
            [
                mock.call(session, 222, 1, 2),
                mock.call(session, 222, 3, 3),
            ],
        )

    def test_iter_rejects_invalid_chunk_size(self):
        col = GSCollection('People')

        with self.assertRaisesRegex(ValueError, "chunk_size"):
            col.iter(chunk_size=0, session=mock.Mock())

    def test_search_iter_empty_result_does_not_fetch_array(self):
        col = GSCollection('People')
        session = mock.Mock()

        with mock.patch.object(
            GSCollection,
            '_search_result_oop',
            autospec=True,
            return_value=gemstone.OOP_NIL,
        ):
            result = list(col.search_iter('@age', 'lt', 25, session=session))

        self.assertEqual(result, [])
        session.perform_oop.assert_not_called()
        session.perform_value.assert_not_called()

    def test_iterator_context_closes_owned_session_on_early_exit(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.perform_oop.return_value = 222
        session.perform_value.return_value = 2
        events = []

        class SessionContext:
            def __enter__(self):
                events.append("enter")
                return session

            def __exit__(self, exc_type, exc_val, exc_tb):
                del exc_type, exc_val, exc_tb
                events.append("exit")

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=SessionContext(),
        ):
            with mock.patch.object(
                GSCollection,
                '_set_oop',
                autospec=True,
                return_value=111,
            ):
                with mock.patch.object(
                    GSCollection,
                    '_records_from_array_range_oop',
                    autospec=True,
                    return_value=[{'@name': 'Alice'}],
                ):
                    with col.iter(chunk_size=1) as iterator:
                        self.assertEqual(next(iterator), {'@name': 'Alice'})

        self.assertEqual(events, ["enter", "exit"])

    def test_search_iter_streams_from_search_result_oop(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.perform_oop.return_value = 222
        session.perform_value.return_value = 1

        with mock.patch.object(
            GSCollection,
            '_search_result_oop',
            autospec=True,
            return_value=777,
        ) as search_result:
            with mock.patch.object(
                GSCollection,
                '_records_from_array_range_oop',
                autospec=True,
                return_value=[{'@name': 'Bob'}],
            ):
                result = list(col.search_iter('@age', 'lt', 25, session=session))

        self.assertEqual(result, [{'@name': 'Bob'}])
        search_result.assert_called_once_with(col, session, '@age', 'lt', 25)
        session.perform_oop.assert_called_once_with(777, 'asArray')

    def test_query_iter_streams_and_applies_remaining_predicates(self):
        col = GSCollection('Bookings')
        query = col.query(BookingRecord).where(lambda booking: booking.status == "booked").where(
            lambda booking: booking.age >= 21
        )

        with mock.patch.object(
            col,
            'search_iter',
            return_value=iter([
                {'@status': 'booked', '@age': 19},
                {'@status': 'booked', '@age': 30},
            ]),
        ) as search_iter:
            result = list(query.iter(chunk_size=32))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].age, 30)
        search_iter.assert_called_once_with(
            '@status',
            'eql',
            'booked',
            chunk_size=32,
            session=None,
        )

    def test_query_iter_closes_underlying_iterator_when_generator_closes(self):
        col = GSCollection('Bookings')
        closed = False

        class ClosingIterator:
            def __init__(self):
                self._items = iter([
                    {'@status': 'booked', '@age': 30},
                    {'@status': 'booked', '@age': 31},
                ])

            def __iter__(self):
                return self

            def __next__(self):
                return next(self._items)

            def close(self):
                nonlocal closed
                closed = True

        with mock.patch.object(col, 'iter', return_value=ClosingIterator()):
            iterator = col.query(BookingRecord).iter()
            self.assertEqual(next(iterator).age, 30)
            iterator.close()

        self.assertTrue(closed)

    def test_list_reads_root_keys_without_pipe_serialization(self):
        session = mock.Mock()
        session.eval.return_value = True
        session.eval_oop.return_value = 999

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(
                GSCollection,
                '_keys_from_dict_oop',
                autospec=True,
                return_value=['People', 'Jobs'],
            ) as keys:
                result = GSCollection.list()

        self.assertEqual(result, ['People', 'Jobs'])
        session.eval.assert_called_once_with("UserGlobals includesKey: #GSQueryRoot")
        session.eval_oop.assert_called_once_with("UserGlobals at: #GSQueryRoot")
        keys.assert_called_once_with(session, 999)


if __name__ == "__main__":
    unittest.main()
