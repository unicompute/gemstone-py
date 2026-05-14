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

    def test_from_env_accepts_stone_name_alias(self):
        with mock.patch.dict(
            os.environ,
            {
                "GS_STONE_NAME": "aliasStone",
                "GS_USERNAME": "alice",
                "GS_PASSWORD": "secret",
            },
            clear=True,
        ):
            config = gemstone.GemStoneConfig.from_env()

        self.assertEqual(config.stone, "aliasStone")

    def test_from_env_prefers_gs_stone_over_alias(self):
        with mock.patch.dict(
            os.environ,
            {
                "GS_STONE": "primaryStone",
                "GS_STONE_NAME": "aliasStone",
                "GS_USERNAME": "alice",
                "GS_PASSWORD": "secret",
            },
            clear=True,
        ):
            config = gemstone.GemStoneConfig.from_env()

        self.assertEqual(config.stone, "primaryStone")

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
    def test_print_string_uses_perform_value_on_remote_object(self):
        session = mock.Mock()
        session.perform_value.return_value = "anObject"
        ref = gemstone.OopRef(0xABC, session)

        result = ref.print_string()

        self.assertEqual(result, "anObject")
        session.perform_value.assert_called_once_with(0xABC, "printString")


class PackagingSmokeTests(unittest.TestCase):
    def test_canonical_package_exports_core_api(self):
        pkg = importlib.import_module("gemstone_py")
        client_mod = importlib.import_module("gemstone_py.client")
        concurrency_mod = importlib.import_module("gemstone_py.concurrency")
        gci_mod = importlib.import_module("gemstone_py._gci")
        provider_mod = importlib.import_module("gemstone_py.session_providers")
        facade_mod = importlib.import_module("gemstone_py.session_facade")
        transactions_mod = importlib.import_module("gemstone_py.transactions")
        web_mod = importlib.import_module("gemstone_py.web")

        self.assertIs(pkg.GemStoneSession, client_mod.GemStoneSession)
        self.assertIs(pkg.TransactionPolicy, client_mod.TransactionPolicy)
        self.assertIs(pkg.session_providers, provider_mod)
        self.assertIs(web_mod.GemStoneSessionProviderEvent, provider_mod.GemStoneSessionProviderEvent)
        self.assertIs(web_mod.GemStoneSessionProvider, provider_mod.GemStoneSessionProvider)
        self.assertIs(
            web_mod.GemStoneSessionProviderSnapshot,
            provider_mod.GemStoneSessionProviderSnapshot,
        )
        self.assertIs(web_mod.GemStoneSessionPool, provider_mod.GemStoneSessionPool)
        self.assertIs(
            web_mod.GemStoneThreadLocalSessionProvider,
            provider_mod.GemStoneThreadLocalSessionProvider,
        )
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
        self.assertIs(pkg.PerformCall, client_mod.PerformCall)
        self.assertIs(pkg.CommitConflictError, concurrency_mod.CommitConflictError)
        self.assertIs(pkg.ConflictDiagnostics, concurrency_mod.ConflictDiagnostics)
        self.assertIs(pkg.ConflictObject, concurrency_mod.ConflictObject)
        self.assertIs(
            pkg.describe_commit_conflict,
            concurrency_mod.describe_commit_conflict,
        )
        self.assertIs(pkg.format_commit_conflict, concurrency_mod.format_commit_conflict)
        self.assertIs(
            pkg.format_conflict_diagnostics,
            concurrency_mod.format_conflict_diagnostics,
        )
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
        self.assertIs(pkg.retrying_transaction, transactions_mod.retrying_transaction)
        self.assertIs(pkg.TransactionRetry, transactions_mod.TransactionRetry)
        self.assertIs(
            pkg.run_transaction_with_retry,
            transactions_mod.run_transaction_with_retry,
        )
        self.assertIs(
            pkg.PersistentRoot,
            importlib.import_module("gemstone_py.persistent_root").PersistentRoot,
        )

    def test_canonical_package_exposes_submodule_aliases(self):
        facade_mod = importlib.import_module("gemstone_py.session_facade")

        self.assertTrue(hasattr(facade_mod, "GemStoneSessionFacade"))


if __name__ == "__main__":
    unittest.main()
