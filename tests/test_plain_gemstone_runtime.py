from pathlib import Path
import unittest


class PlainGemStoneRuntimeSourceTests(unittest.TestCase):
    def test_core_package_does_not_reference_ruby_vm_selectors(self):
        package_dir = Path(__file__).resolve().parents[1] / "gemstone_py"
        forbidden = (
            "RubyContext",
            "rubyConstAt:",
            "rubyAutoload",
            "perform:env:",
            "with:perform:env:",
            "with:with:perform:env:",
            "MagLev",
            "Maglev::",
            "maglev/",
        )

        offenders: list[str] = []
        for path in sorted(package_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(
            offenders,
            [],
            "core gemstone_py runtime should stay plain-GemStone-only",
        )


if __name__ == "__main__":
    unittest.main()
