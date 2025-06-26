from pathlib import Path
import re
from datetime import datetime
from openai import OpenAI
from .debug_utils import DebugLogger

class TodoManager:
    def __init__(self, config, api_key=None, model=None, temperature=0.3):
        """Initialize the todo manager"""
        self.config = config
        
        if self.config.llm_provider == 'deepseek':
            self.client = OpenAI(
                api_key=self.config.deepseek_api_key, 
                base_url="https://api.deepseek.com"
            )
        else:  # default to openai
            self.client = OpenAI(api_key=self.config.openai_api_key)
        
        # Use provided model or default from config
        self.model = model if model is not None else self.config.model
        self.temperature = temperature
    
    def create_system_prompt(self):
        """Create system prompt for todo extraction"""
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

Format your response as a JSON array of task objects, where each object has:
- "task": The task description text (should be clear and actionable)
- "priority": Estimated priority (high, medium, low) based on explicit mentions first, context second
- "context": Brief context about the task (if available)

If no tasks are mentioned, return an empty array.
"""

    def extract_todos(self, transcript_text, project_name):
        """Extract todo items from transcript"""
        user_prompt = f"""
Project: {project_name}

Please extract any tasks, to-dos, or action items from this transcript:

{transcript_text}

Be especially attentive to phrases indicating future actions or tasks.
Look for explicit mentions of priority like "high priority", "urgent", etc. before making priority judgments.

Your response must be a JSON array of task objects, where each object has "task", "priority", and "context" fields.
The response should be a direct array, NOT an object containing a "tasks" array.
For example: [ {{"task": "...", "priority": "...", "context": "..."}}, {{...}} ]

If no tasks are found, return an empty array: []
"""

        try:
            system_prompt = self.create_system_prompt()
            
            # Prepare messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Configure API call with response_format
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=messages,
                response_format={"type": "json_object"}  # Use JSON format for all providers
            )
            
            content = response.choices[0].message.content
            
            # For debugging - save the conversation
            date_str = datetime.now().strftime('%Y-%m-%d')
            if self.config.debug_llm:
                DebugLogger.save_llm_conversation(
                    self.config, 
                    source_type='todo',
                    model=self.model,
                    temperature=self.temperature,
                    messages=messages,
                    response=content,
                    reference_id=f"{date_str}_{project_name}_todos_{self.config.llm_provider}"
                )
            
            # Parse JSON response
            import json
            try:
                tasks = json.loads(content)
                return tasks
            except json.JSONDecodeError:
                # Fallback extraction if JSON parsing fails
                print(f"JSON parse error with content: {content[:100]}...")
                return self._fallback_task_extraction(content)
                
        except Exception as e:
            print(f"Error extracting todo items: {e}")
            return []
        
    def _fallback_task_extraction(self, content):
        """Fallback method to extract tasks if JSON parsing fails"""
        tasks = []
        
        # Look for task patterns in the raw text
        task_pattern = r'"task"\s*:\s*"([^"]+)"'
        priority_pattern = r'"priority"\s*:\s*"([^"]+)"'
        context_pattern = r'"context"\s*:\s*"([^"]+)"'
        
        task_matches = re.findall(task_pattern, content)
        priority_matches = re.findall(priority_pattern, content)
        context_matches = re.findall(context_pattern, content)
        
        # Create task objects from matches
        for i in range(len(task_matches)):
            task = {
                "task": task_matches[i],
                "priority": priority_matches[i] if i < len(priority_matches) else "medium",
                "context": context_matches[i] if i < len(context_matches) else ""
            }
            tasks.append(task)
        
        return tasks
    
    def get_todo_file_path(self, project_name):
        """Get the path to the project's todo list file"""
        project_path = self.config.projects_path / project_name
        todo_path = project_path / "todo.md"
        return todo_path
    
    def _get_priority_value(self, priority):
        """Convert priority string to numeric value for sorting"""
        if priority.lower() == "high":
            return 0
        elif priority.lower() == "medium":
            return 1
        else:  # low or any other value
            return 2
            
    def sort_todos(self, todos):
        """Sort todos by priority (high to low) and then by date added (oldest first)"""
        # We'll use the position in the list as a proxy for date if dates aren't available
        # This maintains the "oldest first" for same-priority items
        return sorted(todos, key=lambda x: self._get_priority_value(x.get("priority", "medium")))
    
    def format_todos_markdown(self, todos, note_date, note_filename):
        """Format todo items as markdown with links to source notes"""
        if not todos:
            return ""
            
        md_content = ""
        
        for todo in todos:
            priority_indicator = ""
            if todo.get("priority") == "high":
                priority_indicator = "🔴 "
            elif todo.get("priority") == "medium":
                priority_indicator = "🟠 "
            elif todo.get("priority") == "low":
                priority_indicator = "🟢 "
                
            task_text = todo["task"]
            context = todo.get("context", "")
            
            # Create link to source note
            source_link = f" *[[{note_filename}|Source]]* "
            
            md_content += f"- [ ] {priority_indicator}{task_text}"
            if context:
                md_content += f" _{context}_"
            md_content += source_link + "\n"
            
        return md_content
    
    def parse_existing_todos(self, content):
        """Parse existing todos from file content"""
        todos = []
        # Regular expression to match todo items with priority indicators and source links
        todo_pattern = r'- \[ \] (🔴|🟠|🟢)? ?(.*?)( _.*?_)? \*\[\[(.*?)\|(Source)\]\]\* *\n'
        
        # If the pattern doesn't match, try alternative patterns
        if not re.search(todo_pattern, content):
            # Try simpler pattern
            todo_pattern = r'- \[ \] (🔴|🟠|🟢)? ?(.*?)( _.*?_)? \*\[\[(.*?)\]\]\* *\n'
        
        for match in re.finditer(todo_pattern, content):
            priority_icon = match.group(1) or ""
            task_text = match.group(2).strip()
            context = match.group(3) or ""
            source = match.group(4) or ""
            
            # Determine priority from icon
            priority = "medium"  # default
            if priority_icon == "🔴":
                priority = "high"
            elif priority_icon == "🟠":
                priority = "medium"
            elif priority_icon == "🟢":
                priority = "low"
                
            # Clean up context (remove leading/trailing underscore)
            if context:
                context = context.strip().strip('_')
                
            todos.append({
                "task": task_text,
                "priority": priority,
                "context": context,
                "source": source
            })
            
        return todos
        
    def add_todos_to_project(self, project_name, new_todos, note_date=None):
        """Add todo items to the project's todo list file"""
        if not new_todos:
            print("No todo items to add")
            return False
        
        # Ensure all todo items are dictionaries
        valid_todos = []
        for todo in new_todos:
            if isinstance(todo, dict) and "task" in todo:
                valid_todos.append(todo)
            elif isinstance(todo, str):
                # Convert string todo to dictionary format
                print(f"Converting string todo to dictionary: {todo[:30]}...")
                valid_todos.append({
                    "task": todo,
                    "priority": "medium",  # Default priority
                    "context": ""          # Empty context
                })
        
        if len(valid_todos) < len(new_todos):
            print(f"⚠️ Note: {len(new_todos) - len(valid_todos)} invalid todo items were skipped")
        
        if not valid_todos:
            print("No valid todo items to add after filtering")
            return False
            
        todo_path = self.get_todo_file_path(project_name)
        date_str = note_date or datetime.now().strftime('%Y-%m-%d')
        
        # Note filename for linking
        note_filename = f"{date_str}_{project_name}"
        
        # Create todo content for new items
        new_todo_content = self.format_todos_markdown(valid_todos, date_str, note_filename)
        
        # Create or update todo file
        if todo_path.exists():
            with open(todo_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
                
            # Check if file has a title, if not add one
            has_title = existing_content.startswith('# ')
            
            # Parse existing todos
            existing_todos = self.parse_existing_todos(existing_content)
            
            # Combine with new todos
            all_todos = existing_todos + valid_todos
            
            # Sort todos
            sorted_todos = self.sort_todos(all_todos)
            
            # Format all todos
            formatted_todos = ""
            for todo in sorted_todos:
                # Ensure todo is a dictionary
                if not isinstance(todo, dict):
                    print(f"⚠️ Skipping invalid todo item: {todo}")
                    continue
                    
                # Get source from existing todo or use the new note filename
                source = todo.get("source", note_filename)
                
                # Format with priority indicator
                priority_indicator = ""
                priority = todo.get("priority", "medium")
                if priority == "high":
                    priority_indicator = "🔴 "
                elif priority == "medium":
                    priority_indicator = "🟠 "
                elif priority == "low":
                    priority_indicator = "🟢 "
                    
                task_text = todo.get("task", "Unknown task")
                context = todo.get("context", "")
                
                # Create link to source note
                source_link = f" *[[{source}|Source]]* "
                
                formatted_todos += f"- [ ] {priority_indicator}{task_text}"
                if context:
                    formatted_todos += f" _{context}_"
                formatted_todos += source_link + "\n"
            
            # Create final content
            if has_title:
                # Extract title and frontmatter if present
                title_match = re.match(r'(---\n.*?\n---\n)?(# .*?\n)', existing_content, re.DOTALL)
                if title_match:
                    frontmatter = title_match.group(1) or ""
                    title = title_match.group(2)
                    todo_content = f"{frontmatter}{title}\n{formatted_todos}"
                else:
                    todo_content = f"---\ntags: [todo, project/{project_name}]\n---\n\n# {project_name} Todo List\n\n{formatted_todos}"
            else:
                todo_content = f"---\ntags: [todo, project/{project_name}]\n---\n\n# {project_name} Todo List\n\n{formatted_todos}"
        else:
            # Create new todo file with title
            todo_content = f"---\ntags: [todo, project/{project_name}]\n---\n\n# {project_name} Todo List\n\n{new_todo_content}"
            
            # Create project directory if it doesn't exist
            project_dir = todo_path.parent
            project_dir.mkdir(parents=True, exist_ok=True)
        
        # Write updated content
        with open(todo_path, 'w', encoding='utf-8') as f:
            f.write(todo_content)
            
        print(f"✅ Added {len(valid_todos)} todo items to {project_name}/todo.md")
        return True