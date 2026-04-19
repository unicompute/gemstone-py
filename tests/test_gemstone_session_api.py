import importlib
import os
import unittest
from unittest import mock

import gemstone_py as gemstone


class GemStoneConfigTests(unittest.TestCase):
    def test_from_env_reads_explicit_settings(self):
        with mock.patch.dict(
            os.environ,
            {
                "GS_STONE": "demoStone",
                "GS_NETLDI": "50377",
                "GS_HOST": "stone.example.com",
                "GS_USERNAME": "alice",
                "GS_PASSWORD": "secret",
                "GS_HOST_USERNAME": "host-user",
                "GS_HOST_PASSWORD": "host-secret",
                "GS_GEM_SERVICE": "gemnetcustom",
                "GS_LIB_PATH": "/tmp/libgcirpc.dylib",
            },
            clear=True,
        ):
            config = gemstone.GemStoneConfig.from_env()

        self.assertEqual(config.stone, "demoStone")
        self.assertEqual(config.netldi, "50377")
        self.assertEqual(config.host, "stone.example.com")
        self.assertEqual(config.username, "alice")
        self.assertEqual(config.password, "secret")
        self.assertEqual(config.host_username, "host-user")
        self.assertEqual(config.host_password, "host-secret")
        self.assertEqual(config.gem_service, "gemnetcustom")
        self.assertEqual(config.lib_path, "/tmp/libgcirpc.dylib")

    def test_from_env_requires_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(gemstone.GemStoneConfigurationError):
                gemstone.GemStoneConfig.from_env()


class GemStoneSessionPolicyTests(unittest.TestCase):
    def _session(self, policy):
        session = gemstone.GemStoneSession(
            username="alice",
            password="secret",
            transaction_policy=policy,
        )
        session._logged_in = True
        session._session_id = 17
        session._lib = mock.Mock()
        return session

    def test_manual_policy_does_not_commit_or_abort_on_clean_exit(self):
        session = self._session(gemstone.TransactionPolicy.MANUAL)

        with mock.patch.object(session, "commit") as commit:
            with mock.patch.object(session, "abort") as abort:
                with mock.patch.object(session, "logout") as logout:
                    session.__exit__(None, None, None)

        commit.assert_not_called()
        abort.assert_not_called()
        logout.assert_called_once_with()

    def test_commit_on_success_commits_on_clean_exit(self):
        session = self._session(gemstone.TransactionPolicy.COMMIT_ON_SUCCESS)

        with mock.patch.object(session, "commit") as commit:
            with mock.patch.object(session, "abort") as abort:
                with mock.patch.object(session, "logout") as logout:
                    session.__exit__(None, None, None)

        commit.assert_called_once_with()
        abort.assert_not_called()
        logout.assert_called_once_with()

    def test_abort_on_exit_aborts_on_clean_exit(self):
        session = self._session(gemstone.TransactionPolicy.ABORT_ON_EXIT)

        with mock.patch.object(session, "commit") as commit:
            with mock.patch.object(session, "abort") as abort:
                with mock.patch.object(session, "logout") as logout:
                    session.__exit__(None, None, None)

        commit.assert_not_called()
        abort.assert_called_once_with()
        logout.assert_called_once_with()

    def test_any_exception_aborts_before_logout(self):
        session = self._session(gemstone.TransactionPolicy.MANUAL)

        with mock.patch.object(session, "abort") as abort:
            with mock.patch.object(session, "logout") as logout:
                session.__exit__(RuntimeError, RuntimeError("boom"), None)

        abort.assert_called_once_with()
        logout.assert_called_once_with()


class OopRefTests(unittest.TestCase):
    def test_print_string_uses_perform_on_remote_object(self):
        session = mock.Mock()
        session.perform.return_value = "anObject"
        ref = gemstone.OopRef(0xABC, session)

        result = ref.print_string()

        self.assertEqual(result, "anObject")
        session.perform.assert_called_once_with(0xABC, "printString")


class PackagingSmokeTests(unittest.TestCase):
    def test_canonical_package_exports_core_api(self):
        pkg = importlib.import_module("gemstone_py")
        client_mod = importlib.import_module("gemstone_py.client")
        gci_mod = importlib.import_module("gemstone_py._gci")
        facade_mod = importlib.import_module("gemstone_py.session_facade")
        web_mod = importlib.import_module("gemstone_py.web")

        self.assertIs(pkg.GemStoneSession, client_mod.GemStoneSession)
        self.assertIs(pkg.TransactionPolicy, client_mod.TransactionPolicy)
        self.assertIs(pkg.GemStoneSessionProviderEvent, web_mod.GemStoneSessionProviderEvent)
        self.assertIs(pkg.GemStoneSessionProvider, web_mod.GemStoneSessionProvider)
        self.assertIs(
            pkg.GemStoneSessionProviderSnapshot,
            web_mod.GemStoneSessionProviderSnapshot,
        )
        self.assertIs(pkg.GemStoneSessionPool, web_mod.GemStoneSessionPool)
        self.assertIs(
            pkg.GemStoneThreadLocalSessionProvider,
            web_mod.GemStoneThreadLocalSessionProvider,
        )
        self.assertIs(pkg.GciErrSType, gci_mod.GciErrSType)
        self.assertEqual(pkg.OOP_TRUE, gci_mod.OOP_TRUE)
        self.assertEqual(pkg.OOP_FALSE, gci_mod.OOP_FALSE)
        self.assertEqual(pkg.OOP_ILLEGAL, gci_mod.OOP_ILLEGAL)
        self.assertIs(pkg.GemStoneSession, client_mod.GemStoneSession)
        self.assertIs(pkg.session_scope, web_mod.session_scope)
        self.assertIs(
            pkg.close_flask_request_session_provider,
            web_mod.close_flask_request_session_provider,
        )
        self.assertIs(
            pkg.flask_request_session_provider_metrics,
            web_mod.flask_request_session_provider_metrics,
        )
        self.assertIs(
            pkg.warm_flask_request_session_provider,
            web_mod.warm_flask_request_session_provider,
        )
        self.assertIs(pkg.GemStoneSessionFacade, facade_mod.GemStoneSessionFacade)
        self.assertIs(
            pkg.PersistentRoot,
            importlib.import_module("gemstone_py.persistent_root").PersistentRoot,
        )

    def test_canonical_package_exposes_submodule_aliases(self):
        facade_mod = importlib.import_module("gemstone_py.session_facade")

        self.assertTrue(hasattr(facade_mod, "GemStoneSessionFacade"))


if __name__ == "__main__":
    unittest.main()
