import io
import json
import unittest
from contextlib import redirect_stdout

import gemstone_py.api_contract as api_contract


class ApiContractTests(unittest.TestCase):
    def test_validate_public_api_checks_supported_exports(self) -> None:
        validated = api_contract.validate_public_api()

        self.assertIn("GemStoneSession", validated)
        self.assertIn("PersistentRoot", validated)
        self.assertIn("benchmark_baseline_register", validated)

    def test_main_emits_json(self) -> None:
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = api_contract.main(["--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertGreater(payload["count"], 0)
        self.assertIn("GemStoneSession", payload["validated_exports"])
        self.assertIn("benchmark_compare_thresholds", payload["validated_behaviors"])
        self.assertIn("benchmark_compare_cli_json", payload["validated_behaviors"])
        self.assertIn("benchmark_baseline_register_cli_json", payload["validated_behaviors"])
        self.assertIn("benchmark_baseline_selection_cli_json", payload["validated_behaviors"])
        self.assertIn("benchmark_baseline_selection", payload["validated_behaviors"])
        self.assertIn("benchmark_baseline_lifecycle", payload["validated_behaviors"])


if __name__ == "__main__":
    unittest.main()
