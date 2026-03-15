import sys
import types
import unittest
from pathlib import Path


openai_stub = types.ModuleType("openai")


class OpenAI:  # pragma: no cover - simple import stub for local tests
    def __init__(self, *args, **kwargs):
        pass


openai_stub.OpenAI = OpenAI
sys.modules.setdefault("openai", openai_stub)

from src.timeline_generator import TimelineGenerator
from src.todo_extractor import TodoExtractor
from src.todo_manager import TodoManager


class SmokeTests(unittest.TestCase):
    def test_extract_date_from_filename_supports_expected_formats(self):
        extractor = TodoExtractor(None, None, None)

        self.assertEqual(
            extractor.extract_date_from_filename("Daily_Log_13-03-2026.m4a"),
            "2026-03-13",
        )
        self.assertEqual(
            extractor.extract_date_from_filename("voice_note_2026-03-13.wav"),
            "2026-03-13",
        )
        self.assertEqual(
            extractor.extract_date_from_filename("notes_13-03-2026.mp3"),
            "2026-03-13",
        )
        self.assertIsNone(extractor.extract_date_from_filename("Daily_Log_31-02-2026.wav"))

    def test_parse_existing_todos_reads_priority_context_and_source(self):
        manager = TodoManager.__new__(TodoManager)
        content = """---
tags: [todo, project/TestProject]
---

# TestProject Todo List

- [ ] 🔴 Fix login bug _after API deploy_ *[[2026-03-10_TestProject|Source]]*
- [ ] 🟢 Review docs *[[2026-03-11_TestProject|Source]]*
"""

        todos = manager.parse_existing_todos(content)

        self.assertEqual(len(todos), 2)
        self.assertEqual(todos[0]["task"], "Fix login bug")
        self.assertEqual(todos[0]["priority"], "high")
        self.assertEqual(todos[0]["context"], "after API deploy")
        self.assertEqual(todos[0]["source"], "2026-03-10_TestProject")
        self.assertEqual(todos[1]["priority"], "low")

    def test_group_notes_by_week_uses_iso_calendar(self):
        generator = TimelineGenerator.__new__(TimelineGenerator)
        daily_notes = {
            "2024-12-30": Path("2024-12-30_TestProject.md"),
            "2025-01-02": Path("2025-01-02_TestProject.md"),
            "2025-01-06": Path("2025-01-06_TestProject.md"),
        }

        grouped = generator.group_notes_by_week(daily_notes)

        self.assertIn((2025, 1), grouped)
        self.assertIn((2025, 2), grouped)
        self.assertEqual(
            set(grouped[(2025, 1)].keys()),
            {"2024-12-30", "2025-01-02"},
        )

    def test_get_week_range_handles_year_boundaries(self):
        generator = TimelineGenerator.__new__(TimelineGenerator)

        week_start, week_end = generator.get_week_range(2025, 1)

        self.assertEqual(week_start.strftime("%Y-%m-%d"), "2024-12-30")
        self.assertEqual(week_end.strftime("%Y-%m-%d"), "2025-01-05")


if __name__ == "__main__":
    unittest.main()
