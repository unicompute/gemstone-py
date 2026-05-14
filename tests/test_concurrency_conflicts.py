import unittest
from unittest import mock

from gemstone_py import inspection
from gemstone_py.concurrency import (
    CommitConflictError,
    ConflictDiagnostics,
    ConflictObject,
    describe_commit_conflict,
    format_commit_conflict,
    format_conflict_diagnostics,
)


class CommitConflictDiagnosticsTests(unittest.TestCase):
    def test_describe_commit_conflict_enriches_oops_with_inspection(self):
        conflict = CommitConflictError("raw conflict report", [101], [202])
        session = mock.Mock()

        with mock.patch(
            "gemstone_py.inspection.inspect_oop",
            side_effect=[
                inspection.InspectionResult(101, "Booking", "booking 1", []),
                inspection.InspectionResult(202, "Customer", "customer 1", []),
            ],
        ) as inspect_oop:
            diagnostics = describe_commit_conflict(conflict, session=session)

        self.assertEqual(diagnostics.report, "raw conflict report")
        self.assertEqual(diagnostics.write_write[0].class_name, "Booking")
        self.assertEqual(diagnostics.write_write[0].summary, "booking 1")
        self.assertEqual(diagnostics.write_dependency[0].class_name, "Customer")
        self.assertEqual(inspect_oop.call_args_list[0].args, (session, 101))
        self.assertEqual(inspect_oop.call_args_list[1].args, (session, 202))

    def test_describe_commit_conflict_can_skip_summaries(self):
        conflict = CommitConflictError("raw conflict report", [101], [])
        session = mock.Mock()

        with mock.patch(
            "gemstone_py.inspection.inspect_oop",
            return_value=inspection.InspectionResult(101, "Booking", "booking 1", []),
        ):
            diagnostics = conflict.diagnostics(session, include_summaries=False)

        self.assertEqual(diagnostics.write_write[0].class_name, "Booking")
        self.assertIsNone(diagnostics.write_write[0].summary)

    def test_describe_commit_conflict_records_inspection_errors(self):
        conflict = CommitConflictError("raw conflict report", [101], [])

        with mock.patch(
            "gemstone_py.inspection.inspect_oop",
            side_effect=RuntimeError("cannot inspect"),
        ):
            diagnostics = describe_commit_conflict(conflict, session=mock.Mock())

        self.assertEqual(diagnostics.write_write[0].inspection_error, "cannot inspect")

    def test_format_commit_conflict_renders_groups_and_report(self):
        conflict = CommitConflictError("line one\nline two", [101], [202])

        text = format_commit_conflict(conflict)

        self.assertIn("Commit conflict", text)
        self.assertIn("Write/write conflicts:", text)
        self.assertIn("0x65 (101)", text)
        self.assertIn("Write/dependency conflicts:", text)
        self.assertIn("0xCA (202)", text)
        self.assertIn("GemStone report:", text)
        self.assertIn("  line two", text)

    def test_format_conflict_diagnostics_includes_class_and_summary(self):
        diagnostics = ConflictDiagnostics(
            report="raw",
            write_write=[
                ConflictObject(
                    oop=101,
                    kind="write/write",
                    class_name="Booking",
                    summary="booking 1",
                )
            ],
            write_dependency=[],
        )

        text = format_conflict_diagnostics(diagnostics)

        self.assertIn("0x65 (101) Booking: booking 1", text)


if __name__ == "__main__":
    unittest.main()
