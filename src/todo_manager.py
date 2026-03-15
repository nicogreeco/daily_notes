from datetime import datetime
from pathlib import Path
import re

from .debug_utils import DebugLogger
from .llm_utils import create_llm_client, parse_json_response


class TodoManager:
    PRIORITY_TO_ICON = {
        "high": "🔴 ",
        "medium": "🟠 ",
        "low": "🟢 ",
    }
    ICON_TO_PRIORITY = {
        "🔴": "high",
        "ðŸ”´": "high",
        "🟠": "medium",
        "ðŸŸ ": "medium",
        "🟢": "low",
        "ðŸŸ¢": "low",
    }
    PRIORITY_ICON_PATTERN = r"(🔴|🟠|🟢|ðŸ”´|ðŸŸ |ðŸŸ¢)?"

    def __init__(self, config, api_key=None, model=None, temperature=0.3):
        """Initialize the todo manager."""
        self.config = config
        self.client = create_llm_client(self.config)
        self.model = model if model is not None else self.config.model
        self.temperature = temperature

    def create_system_prompt(self):
        """Create system prompt for todo extraction."""
        return """You are a task extraction assistant. Your job is to identify tasks, to-dos, and action items
from audio transcript notes. Look for phrases like:
- "things to do tomorrow"
- "next steps"
- "I need to"
- "tomorrow I should focus on"
- "thing to add to the todo list"
- "don't forget to"
- "must remember to"
- "action items"
- "this is important"
- "high priority task"
- "urgent"

Extract ONLY clear, actionable items. If the task is vague, try to make it more specific based on context.
Do not extract general comments, observations, or things already completed.

For task priority:
1. FIRST check for explicit mentions of priority like "high priority", "urgent", "important", "critical", etc.
2. ONLY if no explicit priority is mentioned, derive it from context based on significance
3. Default to "medium" priority if uncertain

Priority levels:
- high: Explicitly mentioned as "urgent", "high priority", "critical", "important", "ASAP", etc.
- medium: Default priority if not specified
- low: Explicitly mentioned as "low priority", "whenever you have time", "nice to have", etc.

Format your response as a JSON object with one key:
- "tasks": an array of task objects

Each task object must have:
- "task": The task description text (should be clear and actionable)
- "priority": Estimated priority (high, medium, low) based on explicit mentions first, context second
- "context": Brief context about the task (if available)

If no tasks are mentioned, return {"tasks": []}.
"""

    def extract_todos(self, transcript_text, project_name):
        """Extract todo items from a transcript."""
        user_prompt = f"""
Project: {project_name}

Please extract any tasks, to-dos, or action items from this transcript:

{transcript_text}

Be especially attentive to phrases indicating future actions or tasks.
Look for explicit mentions of priority like "high priority", "urgent", etc. before making priority judgments.

Your response must be a JSON object with a "tasks" key.
Example: {{"tasks": [{{"task": "...", "priority": "...", "context": "..."}}, {{...}}]}}

If no tasks are found, return {{"tasks": []}}
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

            date_str = datetime.now().strftime("%Y-%m-%d")
            if self.config.debug_llm:
                DebugLogger.save_llm_conversation(
                    self.config,
                    source_type="todo",
                    model=self.model,
                    temperature=self.temperature,
                    messages=messages,
                    response=content,
                    reference_id=f"{date_str}_{project_name}_todos_{self.config.llm_provider}",
                )

            parsed_content = parse_json_response(
                content,
                response_label=f"todo extraction for {project_name}",
                fallback_parser=self._parse_fallback_response,
                default={"tasks": []},
            )

            if isinstance(parsed_content, list):
                tasks = parsed_content
            elif isinstance(parsed_content, dict):
                tasks = parsed_content.get("tasks", [])
            else:
                tasks = []

            if not isinstance(tasks, list):
                print("Warning: todo extraction response did not contain a task list.")
                return []

            return tasks

        except Exception as error:
            print(f"Error extracting todo items: {error}")
            return []

    def _parse_fallback_response(self, content):
        return {"tasks": self._fallback_task_extraction(content)}

    def _fallback_task_extraction(self, content):
        """Fallback method to extract tasks if JSON parsing fails."""
        tasks = []
        task_pattern = r'"task"\s*:\s*"([^"]+)"'
        priority_pattern = r'"priority"\s*:\s*"([^"]+)"'
        context_pattern = r'"context"\s*:\s*"([^"]+)"'

        task_matches = re.findall(task_pattern, content)
        priority_matches = re.findall(priority_pattern, content)
        context_matches = re.findall(context_pattern, content)

        for index in range(len(task_matches)):
            tasks.append(
                {
                    "task": task_matches[index],
                    "priority": priority_matches[index] if index < len(priority_matches) else "medium",
                    "context": context_matches[index] if index < len(context_matches) else "",
                }
            )

        return tasks

    def get_todo_file_path(self, project_name):
        """Get the path to a project's todo list."""
        project_path = self.config.projects_path / project_name
        return project_path / "todo.md"

    def _get_priority_value(self, priority):
        """Convert priority string to numeric value for sorting."""
        if priority.lower() == "high":
            return 0
        if priority.lower() == "medium":
            return 1
        return 2

    def _priority_to_icon(self, priority):
        return self.PRIORITY_TO_ICON.get(priority, "")

    def _icon_to_priority(self, priority_icon):
        return self.ICON_TO_PRIORITY.get(priority_icon, "medium")

    def sort_todos(self, todos):
        """Sort todos by priority (high to low)."""
        return sorted(todos, key=lambda item: self._get_priority_value(item.get("priority", "medium")))

    def format_todos_markdown(self, todos, note_date, note_filename):
        """Format todo items as markdown with links to source notes."""
        if not todos:
            return ""

        md_content = ""
        for todo in todos:
            priority_indicator = self._priority_to_icon(todo.get("priority"))
            task_text = todo["task"]
            context = todo.get("context", "")
            source_link = f" *[[{note_filename}|Source]]* "

            md_content += f"- [ ] {priority_indicator}{task_text}"
            if context:
                md_content += f" _{context}_"
            md_content += source_link + "\n"

        return md_content

    def parse_existing_todos(self, content):
        """Parse existing todos from file content."""
        todos = []
        todo_pattern = (
            rf'- \[ \] {self.PRIORITY_ICON_PATTERN} ?(.*?)( _.*?_)? \*\[\[(.*?)\|(Source)\]\]\* *\n'
        )

        if not re.search(todo_pattern, content):
            todo_pattern = (
                rf'- \[ \] {self.PRIORITY_ICON_PATTERN} ?(.*?)( _.*?_)? \*\[\[(.*?)\]\]\* *\n'
            )

        for match in re.finditer(todo_pattern, content):
            priority_icon = match.group(1) or ""
            task_text = match.group(2).strip()
            context = match.group(3) or ""
            source = match.group(4) or ""

            if context:
                context = context.strip().strip("_")

            todos.append(
                {
                    "task": task_text,
                    "priority": self._icon_to_priority(priority_icon),
                    "context": context,
                    "source": source,
                }
            )

        return todos

    def add_todos_to_project(self, project_name, new_todos, note_date=None):
        """Add todo items to the project's todo list file."""
        if not new_todos:
            print("No todo items to add")
            return False

        valid_todos = []
        for todo in new_todos:
            if isinstance(todo, dict) and "task" in todo:
                valid_todos.append(todo)
            elif isinstance(todo, str):
                print(f"Converting string todo to dictionary: {todo[:30]}...")
                valid_todos.append({"task": todo, "priority": "medium", "context": ""})

        if len(valid_todos) < len(new_todos):
            print(f"Warning: {len(new_todos) - len(valid_todos)} invalid todo items were skipped")

        if not valid_todos:
            print("No valid todo items to add after filtering")
            return False

        todo_path = self.get_todo_file_path(project_name)
        date_str = note_date or datetime.now().strftime("%Y-%m-%d")
        note_filename = f"{date_str}_{project_name}"

        new_todo_content = self.format_todos_markdown(valid_todos, date_str, note_filename)

        if todo_path.exists():
            with open(todo_path, "r", encoding="utf-8") as file_handle:
                existing_content = file_handle.read()

            has_title = existing_content.startswith("# ")
            existing_todos = self.parse_existing_todos(existing_content)
            all_todos = self.sort_todos(existing_todos + valid_todos)

            formatted_todos = ""
            for todo in all_todos:
                if not isinstance(todo, dict):
                    print(f"Warning: Skipping invalid todo item: {todo}")
                    continue

                source = todo.get("source", note_filename)
                priority_indicator = self._priority_to_icon(todo.get("priority", "medium"))
                task_text = todo.get("task", "Unknown task")
                context = todo.get("context", "")
                source_link = f" *[[{source}|Source]]* "

                formatted_todos += f"- [ ] {priority_indicator}{task_text}"
                if context:
                    formatted_todos += f" _{context}_"
                formatted_todos += source_link + "\n"

            if has_title:
                title_match = re.match(r"(---\n.*?\n---\n)?(# .*?\n)", existing_content, re.DOTALL)
                if title_match:
                    frontmatter = title_match.group(1) or ""
                    title = title_match.group(2)
                    todo_content = f"{frontmatter}{title}\n{formatted_todos}"
                else:
                    todo_content = (
                        f"---\ntags: [todo, project/{project_name}]\n---\n\n"
                        f"# {project_name} Todo List\n\n{formatted_todos}"
                    )
            else:
                todo_content = (
                    f"---\ntags: [todo, project/{project_name}]\n---\n\n"
                    f"# {project_name} Todo List\n\n{formatted_todos}"
                )
        else:
            todo_content = (
                f"---\ntags: [todo, project/{project_name}]\n---\n\n"
                f"# {project_name} Todo List\n\n{new_todo_content}"
            )
            todo_path.parent.mkdir(parents=True, exist_ok=True)

        with open(todo_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(todo_content)

        print(f"Added {len(valid_todos)} todo items to {project_name}/todo.md")
        return True
