import contextlib
import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.gsquery import GSCollection


class GSCollectionHelpersTests(unittest.TestCase):
    def test_collection_member_oops_reads_via_as_array(self):
        session = mock.Mock()
        session.perform_oop.side_effect = [500, 101, 102]
        session.perform.return_value = 2

        result = GSCollection._collection_member_oops(session, 123)

        self.assertEqual(result, [101, 102])
        self.assertEqual(session.perform_oop.call_args_list, [
            mock.call(123, 'asArray'),
            mock.call(500, 'at:', gemstone._python_to_smallint(1)),
            mock.call(500, 'at:', gemstone._python_to_smallint(2)),
        ])
        session.perform.assert_called_once_with(500, 'size')

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

    def test_keys_from_dict_oop_reads_keys_without_serializing_oops(self):
        session = mock.Mock()
        session.perform_oop.side_effect = [600, 600, 701, 702]
        session.perform.return_value = 2
        session._marshal.side_effect = ['People', 'Jobs']

        result = GSCollection._keys_from_dict_oop(session, 123)

        self.assertEqual(result, ['People', 'Jobs'])
        self.assertEqual(session.perform_oop.call_args_list, [
            mock.call(123, 'keys'),
            mock.call(600, 'asArray'),
            mock.call(600, 'at:', gemstone._python_to_smallint(1)),
            mock.call(600, 'at:', gemstone._python_to_smallint(2)),
        ])


class GSCollectionQueryTests(unittest.TestCase):
    def test_search_oops_uses_indexed_perform_path(self):
        col = GSCollection('People')
        session = mock.Mock()
        session.new_symbol.return_value = 444
        session.perform_oop.return_value = 555

        with mock.patch.object(GSCollection, '_ensure_root', autospec=True):
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111):
                with mock.patch.object(GSCollection, '_path_array_oop', autospec=True, return_value=222):
                    with mock.patch.object(GSCollection, '_collection_member_oops', autospec=True, return_value=[7, 8]) as member_oops:
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
            with mock.patch.object(GSCollection, '_set_oop', autospec=True, return_value=111):
                with mock.patch.object(GSCollection, '_path_array_oop', autospec=True, return_value=222):
                    with mock.patch.object(GSCollection, '_collection_member_oops', autospec=True, return_value=[9]) as member_oops:
                        with mock.patch('gemstone_py.gsquery._to_oop', return_value=333):
                            result = col._search_oops(session, '@age', 'lt', 25)

        self.assertEqual(result, [9])
        session.eval_oop.assert_called_once()
        self.assertIn("select: [:e |", session.eval_oop.call_args.args[0])
        member_oops.assert_called_once_with(session, 666)

    def test_list_reads_root_keys_without_pipe_serialization(self):
        session = mock.Mock()
        session.eval.return_value = True
        session.eval_oop.return_value = 999

        with mock.patch(
            'gemstone_py.gsquery._session',
            return_value=contextlib.nullcontext(session),
        ):
            with mock.patch.object(GSCollection, '_keys_from_dict_oop', autospec=True, return_value=['People', 'Jobs']) as keys:
                result = GSCollection.list()

        self.assertEqual(result, ['People', 'Jobs'])
        session.eval.assert_called_once_with("UserGlobals includesKey: #GSQueryRoot")
        session.eval_oop.assert_called_once_with("UserGlobals at: #GSQueryRoot")
        keys.assert_called_once_with(session, 999)


if __name__ == "__main__":
    unittest.main()
