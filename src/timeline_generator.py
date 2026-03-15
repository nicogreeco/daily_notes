import os
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .debug_utils import DebugLogger
from .llm_utils import create_llm_client, parse_json_response


class TimelineGenerator:
    PRIORITY_ICON_PATTERN = r"(🔴|🟠|🟢|ðŸ”´|ðŸŸ |ðŸŸ¢)?"

    def __init__(self, config, api_key: str = None, model: str = None, temperature: float = 0.3):
        """Initialize timeline generator."""
        self.config = config
        self.client = create_llm_client(self.config)
        self.model = model if model is not None else self.config.weekly_summary_model
        self.temperature = temperature

    def get_week_number(self, date_str: str) -> Tuple[int, int]:
        """Get year and ISO week number from a YYYY-MM-DD string."""
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
        iso_year, iso_week, _ = parsed_date.isocalendar()
        return iso_year, iso_week

    def get_week_range(self, year: int, week: int) -> Tuple[datetime, datetime]:
        """Get the Monday-Sunday range for an ISO week."""
        first_day = date.fromisocalendar(year, week, 1)
        last_day = date.fromisocalendar(year, week, 7)
        return (
            datetime.combine(first_day, time.min),
            datetime.combine(last_day, time.min),
        )

    def get_week_identifier(self, year: int, week: int) -> str:
        """Get a stable identifier like 2025-W01."""
        return f"{year}-W{week:02d}"

    def _icon_to_priority(self, priority_icon: str) -> str:
        if priority_icon in {"🔴", "ðŸ”´"}:
            return "high"
        if priority_icon in {"🟠", "ðŸŸ "}:
            return "medium"
        if priority_icon in {"🟢", "ðŸŸ¢"}:
            return "low"
        return "medium"

    def _priority_to_icon(self, priority: str) -> str:
        if priority == "high":
            return "🔴 "
        if priority == "medium":
            return "🟠 "
        if priority == "low":
            return "🟢 "
        return ""

    def find_project_daily_notes(self, project_name: str) -> Dict[str, Path]:
        """Find all daily note files for a specific project."""
        daily_notes = {}
        pattern = re.compile(r"(\d{4}-\d{2}-\d{2})_" + re.escape(project_name) + r"(?:_\d+)?\.md")

        for file_path in self.config.daily_notes_path.glob("*.md"):
            match = pattern.match(file_path.name)
            if match:
                daily_notes[match.group(1)] = file_path

        return daily_notes

    def group_notes_by_week(self, daily_notes: Dict[str, Path]) -> Dict[Tuple[int, int], Dict[str, Path]]:
        """Group daily notes by ISO week."""
        weekly_notes = {}

        for date_str, file_path in daily_notes.items():
            year_week = self.get_week_number(date_str)
            weekly_notes.setdefault(year_week, {})
            weekly_notes[year_week][date_str] = file_path

        return weekly_notes

    def get_missing_weeks(self, project_name: str) -> List[Tuple[int, int]]:
        """Get weeks that have daily notes but no summary file yet."""
        daily_notes = self.find_project_daily_notes(project_name)
        if not daily_notes:
            print(f"No daily notes found for project: {project_name}")
            return []

        weekly_notes = self.group_notes_by_week(daily_notes)
        timeline_path = self.config.projects_path / project_name / "timeline"
        timeline_path.mkdir(parents=True, exist_ok=True)

        missing_weeks = []
        for year, week in weekly_notes.keys():
            week_file = timeline_path / f"{self.get_week_identifier(year, week)}.md"
            if not week_file.exists():
                missing_weeks.append((year, week))

        missing_weeks.sort()
        return missing_weeks

    def read_daily_note_content(self, note_path: Path) -> Dict[str, str]:
        """Read a daily note and extract the key sections used for weekly summaries."""
        if not note_path.exists():
            return {
                "date": note_path.stem.split("_")[0],
                "summary": "Note file not found",
                "completed": "",
                "blockers": "",
                "next_steps": "",
                "thoughts": "",
            }

        with open(note_path, "r", encoding="utf-8") as file_handle:
            content = file_handle.read()

        sections = {
            "date": note_path.stem.split("_")[0],
            "summary": "",
            "completed": "",
            "blockers": "",
            "next_steps": "",
            "thoughts": "",
        }

        patterns = {
            "summary": r"## .*?Summary\s+(.*?)(?=##|\Z)",
            "completed": r"## .*?Completed Today\s+(.*?)(?=##|\Z)",
            "blockers": r"## .*?In Progress / Blockers\s+(.*?)(?=##|\Z)",
            "next_steps": r"## .*?Next Steps\s+(.*?)(?=##|\Z)",
            "thoughts": r"## .*?Thoughts & Ideas\s+(.*?)(?=##|\Z|---)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                sections[key] = match.group(1).strip()

        return sections

    def create_system_prompt(self) -> str:
        """Create the system prompt for weekly summary generation."""
        return """You are a professional project timeline assistant. Your task is to create weekly summaries of daily work logs.

Given multiple daily work notes for a project within a week, analyze them and create a structured weekly summary with these sections:

1. Week Summary: A concise 3-5 sentence overview of the week's work
2. Key Accomplishments: Major tasks completed, features implemented, or milestones reached
3. Insights & Thoughts: Important ideas, learnings, or reflections from the week
4. Progress Indicators: Current blockers and their status
5. Next Week Focus: A brief 2-line suggestion of what should be prioritized next week

Guidelines:
- Start sentences with specific actions, findings, or results rather than generic statements
- Avoid phrases like "significant progress was made", "work was done", "efforts were focused"
- Use concrete verbs: "implemented", "debugged", "analyzed", "discovered", "resolved"
- Be specific about technical details, methods, tools, and outcomes
- Mention exact features, algorithms, or components worked on
- Include specific metrics, errors resolved, or experiments conducted
- Replace vague terms like "complexity", "various aspects", "initial uncertainties" with concrete descriptions
- Focus on what was actually built, fixed, tested, or learned
- Connect daily accomplishments into a coherent technical narrative
- Write as if reporting to technical stakeholders who want concrete details

Format your response as a JSON object with these keys: week_summary, accomplishments, insights, blockers, next_focus
Each key should contain a string value with markdown formatting.
For bullet points, use a single string with each item prefixed by "- " and separated by "\\n".
Do NOT return arrays/lists for any field, only strings.
If a section has no relevant content, use the string "None applicable".
"""

    def generate_weekly_summary(
        self,
        project_name: str,
        year: int,
        week: int,
        notes_content: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """Generate a weekly summary from grouped daily notes."""
        formatted_notes = []
        for note in notes_content:
            formatted_notes.append(
                "\n".join(
                    [
                        f"Date: {note['date']}",
                        f"Summary: {note['summary']}",
                        f"Completed: {note['completed']}",
                        f"Blockers: {note['blockers']}",
                        f"Next Steps: {note['next_steps']}",
                        f"Thoughts: {note['thoughts']}",
                    ]
                )
            )

        week_start, week_end = self.get_week_range(year, week)
        notes_text = "\n---\n".join(formatted_notes)
        user_prompt = f"""
Project: {project_name}
Week: {year}-W{week:02d} ({week_start.strftime("%Y-%m-%d")} to {week_end.strftime("%Y-%m-%d")})

Daily Notes:
{notes_text}

Please analyze these daily notes and generate a weekly summary.
"""

        try:
            messages = [
                {"role": "system", "content": self.create_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=messages,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            if self.config.debug_llm:
                DebugLogger.save_llm_conversation(
                    self.config,
                    source_type="weekly",
                    model=self.model,
                    temperature=self.temperature,
                    messages=messages,
                    response=content,
                    reference_id=f"{self.get_week_identifier(year, week)}_{project_name}",
                )

            result = parse_json_response(
                content,
                response_label=f"weekly summary for {project_name}",
                fallback_parser=self._parse_fallback_response,
                default=self._create_error_response(),
            )
            return self._normalize_response_format(result)

        except Exception as error:
            print(f"Error generating weekly summary: {error}")
            return self._create_error_response()

    def _normalize_response_format(self, parsed_content):
        """Normalize response format to the strings expected by the template."""
        if not isinstance(parsed_content, dict):
            return self._create_error_response()

        normalized = {}
        for field in ["week_summary", "accomplishments", "insights", "blockers", "next_focus"]:
            value = parsed_content.get(field, "None applicable")

            if isinstance(value, list):
                value = "\n".join(value)

            if value == "":
                value = "None applicable"

            if field not in {"week_summary", "next_focus"} and value != "None applicable":
                if not value.startswith("- "):
                    value = "- " + value.replace("\n", "\n- ")

            normalized[field] = value

        return normalized

    def _parse_fallback_response(self, content: str) -> Dict[str, str]:
        """Fallback parser if JSON parsing fails."""
        sections = {
            "week_summary": "Error parsing summary",
            "accomplishments": "- Error parsing accomplishments",
            "insights": "- Error parsing insights",
            "blockers": "- Error parsing blockers",
            "next_focus": "Error parsing next focus",
        }

        patterns = {
            "week_summary": r'week_summary["\s:]+([^"]+)',
            "accomplishments": r'accomplishments["\s:]+([^"]+)',
            "insights": r'insights["\s:]+([^"]+)',
            "blockers": r'blockers["\s:]+([^"]+)',
            "next_focus": r'next_focus["\s:]+([^"]+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                sections[key] = match.group(1).strip()

        return sections

    def _create_error_response(self) -> Dict[str, str]:
        """Create a fallback weekly summary payload."""
        return {
            "week_summary": "Error generating weekly summary",
            "accomplishments": "- Could not process daily notes",
            "insights": "- Error occurred during processing",
            "blockers": "- Please review daily notes manually",
            "next_focus": "Manual review needed",
        }

    def get_weekly_template(self) -> str:
        """Get the markdown template for weekly summaries."""
        return """---
tags: [timeline, weekly-summary, project/{project_name}]
week: {week_id}
date_range: {date_range}
---

# Week {week_id}: {date_range} - {project_name}

## Week Summary
{week_summary}

## Key Accomplishments
{accomplishments}

## Insights & Thoughts
{insights}

## Progress Indicators
{blockers}

## Next Week Focus
{next_focus}

{completed_todos_section}

## Daily Notes References
{daily_notes_links}
"""

    def find_completed_todos(self, project_name: str) -> List[Dict]:
        """Find completed todos in the project's todo list."""
        todo_path = self.config.projects_path / project_name / "todo.md"
        if not todo_path.exists():
            return []

        completed_todos = []
        try:
            with open(todo_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()

            todo_pattern = (
                rf'- \[x\] {self.PRIORITY_ICON_PATTERN} ?(.*?)( _.*?_)? \*\[\[(.*?)\|(Source)\]\]\* *\n'
            )
            if not re.search(todo_pattern, content):
                todo_pattern = (
                    rf'- \[x\] {self.PRIORITY_ICON_PATTERN} ?(.*?)( _.*?_)? \*\[\[(.*?)\]\]\* *\n'
                )

            for match in re.finditer(todo_pattern, content):
                priority_icon = match.group(1) or ""
                task_text = match.group(2).strip()
                context = match.group(3) or ""
                source = match.group(4) or ""

                if context:
                    context = context.strip().strip("_")

                completed_todos.append(
                    {
                        "task": task_text,
                        "priority": self._icon_to_priority(priority_icon),
                        "context": context,
                        "source": source,
                    }
                )

            return completed_todos
        except Exception as error:
            print(f"Error finding completed todos: {error}")
            return []

    def clean_completed_todos(self, project_name: str) -> int:
        """Remove completed todos from the project todo list."""
        todo_path = self.config.projects_path / project_name / "todo.md"
        if not todo_path.exists():
            return 0

        try:
            with open(todo_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()

            new_content = re.sub(
                rf'- \[x\] {self.PRIORITY_ICON_PATTERN} ?.*?( _.*?_)? \*\[\[.*?\|Source\]\]\* *\n',
                "",
                content,
            )

            if new_content == content:
                new_content = re.sub(
                    rf'- \[x\] {self.PRIORITY_ICON_PATTERN} ?.*?( _.*?_)? \*\[\[.*?\]\]\* *\n',
                    "",
                    content,
                )

            removed_count = content.count("- [x]")

            with open(todo_path, "w", encoding="utf-8") as file_handle:
                file_handle.write(new_content)

            return removed_count
        except Exception as error:
            print(f"Error cleaning completed todos: {error}")
            return 0

    def create_weekly_summary_file(self, project_name: str, year: int, week: int) -> Optional[Path]:
        """Create a weekly summary file for a project and week."""
        daily_notes = self.find_project_daily_notes(project_name)
        if not daily_notes:
            print(f"No daily notes found for project: {project_name}")
            return None

        weekly_notes = self.group_notes_by_week(daily_notes)
        year_week = (year, week)
        if year_week not in weekly_notes:
            print(f"No daily notes found for week {year}-W{week:02d} in project {project_name}")
            return None

        week_start, week_end = self.get_week_range(year, week)
        week_id = self.get_week_identifier(year, week)

        notes_content = []
        for _, file_path in sorted(weekly_notes[year_week].items()):
            notes_content.append(self.read_daily_note_content(file_path))

        summary = self.generate_weekly_summary(project_name, year, week, notes_content)
        completed_todos = self.find_completed_todos(project_name)
        cleaned_count = self.clean_completed_todos(project_name)

        completed_todos_section = ""
        if self.config.track_completed_todos and completed_todos:
            completed_todos_section = "## Completed Tasks\n"
            for todo in completed_todos:
                completed_todos_section += f"- {self._priority_to_icon(todo.get('priority'))}{todo['task']}"
                if todo.get("context"):
                    completed_todos_section += f" _{todo['context']}_"
                completed_todos_section += f" *[[{todo.get('source', '')}|Source]]* \n"
            completed_todos_section += "\n"

        daily_links = []
        for date_str, file_path in sorted(weekly_notes[year_week].items()):
            daily_links.append(f"- [{date_str}: Daily Log]({os.path.basename(file_path)})")

        content = self.get_weekly_template().format(
            week_id=week_id,
            date_range=f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}",
            project_name=project_name,
            week_summary=summary["week_summary"],
            accomplishments=summary["accomplishments"],
            insights=summary["insights"],
            blockers=summary["blockers"],
            next_focus=summary["next_focus"],
            completed_todos_section=completed_todos_section,
            daily_notes_links="\n".join(daily_links),
        )

        timeline_path = self.config.projects_path / project_name / "timeline"
        timeline_path.mkdir(parents=True, exist_ok=True)

        week_file = timeline_path / f"{week_id}.md"
        with open(week_file, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)

        print(f"Created weekly summary: {week_file.name}")
        if cleaned_count > 0:
            print(f"Cleaned {cleaned_count} completed todos from todo list")

        return week_file

    def update_timeline_index(self, project_name: str) -> Optional[Path]:
        """Update the master timeline index file for a project."""
        timeline_path = self.config.projects_path / project_name / "timeline"
        if not timeline_path.exists():
            print(f"No timeline folder found for project: {project_name}")
            return None

        weekly_files = []
        for file_path in timeline_path.glob("*.md"):
            if file_path.name == "timeline_index.md":
                continue

            match = re.match(r"(\d{4})-W(\d{2})\.md", file_path.name)
            if not match:
                continue

            year = int(match.group(1))
            week = int(match.group(2))
            week_start, week_end = self.get_week_range(year, week)

            with open(file_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()

            summary = ""
            summary_match = re.search(r"## Week Summary\s+(.*?)(?=##|\Z)", content, re.DOTALL)
            if summary_match:
                summary = " ".join(summary_match.group(1).strip().split())

            weekly_files.append(
                {
                    "file": file_path,
                    "year": year,
                    "week": week,
                    "date_range": f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}",
                    "summary": summary,
                }
            )

        if not weekly_files:
            print(f"No weekly summaries found for project: {project_name}")
            return None

        weekly_files.sort(key=lambda entry: (entry["year"], entry["week"]), reverse=True)

        index_content = f"# {project_name} Timeline\n\n## Recent Weeks\n"
        for entry in weekly_files[:12]:
            week_id = self.get_week_identifier(entry["year"], entry["week"])
            index_content += f"- [{week_id}: {entry['date_range']}]({week_id}.md) - {entry['summary']}\n"

        if len(weekly_files) > 12:
            index_content += "\n## All Weeks\n"
            years = {}
            for entry in weekly_files:
                years.setdefault(entry["year"], []).append(entry)

            for year in sorted(years.keys(), reverse=True):
                index_content += f"\n### {year}\n"
                for entry in sorted(years[year], key=lambda item: item["week"], reverse=True):
                    week_id = self.get_week_identifier(entry["year"], entry["week"])
                    index_content += f"- [Week {entry['week']:02d}: {entry['date_range']}]({week_id}.md)\n"

        index_file = timeline_path / "timeline_index.md"
        with open(index_file, "w", encoding="utf-8") as file_handle:
            file_handle.write(index_content)

        print(f"Updated timeline index for project: {project_name}")
        return index_file

    def generate_missing_weeks(self, project_name: str) -> int:
        """Generate timeline entries for all missing weeks of one project."""
        missing_weeks = self.get_missing_weeks(project_name)
        if not missing_weeks:
            print(f"No missing timeline entries for project: {project_name}")
            return 0

        print(f"Generating {len(missing_weeks)} missing timeline entries for project: {project_name}")

        count = 0
        for year, week in missing_weeks:
            week_id = self.get_week_identifier(year, week)
            print(f"Processing {week_id}...")
            if self.create_weekly_summary_file(project_name, year, week):
                count += 1

        if count > 0:
            self.update_timeline_index(project_name)

        return count

    def process_all_projects(self) -> Dict[str, int]:
        """Generate missing timeline entries for every project."""
        available_projects = self.config.get_available_projects()
        if not available_projects:
            print("No projects found")
            return {}

        results = {}
        for project in available_projects:
            print(f"\nProcessing project: {project}")
            results[project] = self.generate_missing_weeks(project)

        return results
