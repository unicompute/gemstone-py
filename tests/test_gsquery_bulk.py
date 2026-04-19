import contextlib
import unittest
from unittest import mock

from gemstone_py.gsquery import GSCollection


class GSCollectionBulkInsertTests(unittest.TestCase):
    def test_bulk_insert_reuses_one_collection_lookup(self):
        col = GSCollection('People')
        session = mock.Mock()
        elements = [{'@name': 'alice'}, {'@name': 'bob'}]

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111) as set_oop:
                with mock.patch.object(GSCollection, '_insert_into_set_oop', autospec=True) as insert_into:
                    total = col.bulk_insert(elements)

        self.assertEqual(total, 2)
        set_oop.assert_called_once_with(col, session)
        self.assertEqual(
            insert_into.call_args_list,
            [
                mock.call(col, session, 111, {'@name': 'alice'}),
                mock.call(col, session, 111, {'@name': 'bob'}),
            ],
        )

    def test_bulk_insert_accepts_generators(self):
        col = GSCollection('People')
        session = mock.Mock()

        def records():
            yield {'@name': 'alice'}
            yield {'@name': 'bob'}
            yield {'@name': 'carol'}

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111):
                with mock.patch.object(GSCollection, '_insert_into_set_oop', autospec=True) as insert_into:
                    total = col.bulk_insert(records())

        self.assertEqual(total, 3)
        self.assertEqual(insert_into.call_count, 3)

    def test_replace_all_reuses_one_collection_lookup_after_reset(self):
        col = GSCollection('People')
        session = mock.Mock()
        elements = [{'@name': 'alice'}, {'@name': 'bob'}]

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_ensure_root', autospec=True) as ensure_root:
                with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=222) as set_oop:
                    with mock.patch.object(GSCollection, '_insert_into_set_oop', autospec=True) as insert_into:
                        col.replace_all(elements)

        ensure_root.assert_called_once_with(col, session)
        session.eval.assert_called_once()
        set_oop.assert_called_once_with(col, session)
        self.assertEqual(
            insert_into.call_args_list,
            [
                mock.call(col, session, 222, {'@name': 'alice'}),
                mock.call(col, session, 222, {'@name': 'bob'}),
            ],
        )

    def test_bulk_delete_where_reuses_one_collection_lookup(self):
        col = GSCollection('People')
        session = mock.Mock()

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111) as set_oop:
                with mock.patch.object(GSCollection, '_search_oops', autospec=True, side_effect=[[201], [202, 203]]) as search:
                    with mock.patch.object(GSCollection, '_remove_member_oops', autospec=True, side_effect=[1, 2]) as remove:
                        total = col.bulk_delete_where('@id', ['a', 'b', 'a'])

        self.assertEqual(total, 3)
        set_oop.assert_called_once_with(col, session)
        self.assertEqual(
            search.call_args_list,
            [
                mock.call(col, session, '@id', 'eql', 'a'),
                mock.call(col, session, '@id', 'eql', 'b'),
            ],
        )
        self.assertEqual(
            remove.call_args_list,
            [
                mock.call(col, session, 111, [201]),
                mock.call(col, session, 111, [202, 203]),
            ],
        )

    def test_bulk_upsert_unique_reuses_one_collection_lookup(self):
        col = GSCollection('People')
        session = mock.Mock()
        elements = [
            {'@id': 'a', '@name': 'alice'},
            {'@id': 'b', '@name': 'bob'},
            {'@id': 'a', '@name': 'alice-2'},
        ]

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111) as set_oop:
                with mock.patch.object(GSCollection, '_search_oops', autospec=True, side_effect=[[301], [302]]) as search:
                    with mock.patch.object(GSCollection, '_remove_member_oops', autospec=True) as remove:
                        with mock.patch.object(GSCollection, '_insert_into_set_oop', autospec=True) as insert_into:
                            total = col.bulk_upsert_unique('@id', elements)

        self.assertEqual(total, 2)
        set_oop.assert_called_once_with(col, session)
        self.assertEqual(
            search.call_args_list,
            [
                mock.call(col, session, '@id', 'eql', 'a'),
                mock.call(col, session, '@id', 'eql', 'b'),
            ],
        )
        self.assertEqual(
            insert_into.call_args_list,
            [
                mock.call(col, session, 111, {'@id': 'a', '@name': 'alice-2'}),
                mock.call(col, session, 111, {'@id': 'b', '@name': 'bob'}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
