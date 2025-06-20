from pathlib import Path
from datetime import datetime, timedelta
import re
from typing import List, Dict, Tuple, Optional
import os
from openai import OpenAI
import json

class TimelineGenerator:
    def __init__(self, config, api_key: str = None, model: str = None, temperature: float = 0.3):
        """Initialize timeline generator"""
        self.config = config
        
        if self.config.llm_provider == 'deepseek':
            self.client = OpenAI(
                api_key=self.config.deepseek_api_key, 
                base_url="https://api.deepseek.com"
            )
        else:  # default to openai
            self.client = OpenAI(api_key=self.config.openai_api_key)
        
        # Use provided model or default from config
        self.model = model if model is not None else self.config.weekly_summary_model
        self.temperature = temperature
    
    def get_week_number(self, date_str: str) -> Tuple[int, int]:
        """Get year and week number from date string (YYYY-MM-DD)"""
        date = datetime.strptime(date_str, '%Y-%m-%d')
        year = date.isocalendar()[0]
        week = date.isocalendar()[1]
        return (year, week)
    
    def get_week_range(self, year: int, week: int) -> Tuple[datetime, datetime]:
        """Get start and end dates for a week"""
        # Find the first day of the given week
        first_day = datetime.strptime(f'{year}-{week}-1', '%Y-%W-%w')
        if first_day.weekday() != 0:  # If not Monday
            first_day = first_day - timedelta(days=first_day.weekday())
        
        last_day = first_day + timedelta(days=6)
        return (first_day, last_day)
    
    def find_project_daily_notes(self, project_name: str) -> Dict[str, Path]:
        """Find all daily notes for a specific project"""
        daily_notes = {}
        
        # Regex pattern for daily note filenames: YYYY-MM-DD_ProjectName.md
        pattern = re.compile(r'(\d{4}-\d{2}-\d{2})_' + re.escape(project_name) + r'(?:_\d+)?\.md')
        
        # Scan the daily notes folder
        for file_path in self.config.daily_notes_path.glob('*.md'):
            match = pattern.match(file_path.name)
            if match:
                date_str = match.group(1)
                daily_notes[date_str] = file_path
        
        return daily_notes
    
    def group_notes_by_week(self, daily_notes: Dict[str, Path]) -> Dict[Tuple[int, int], Dict[str, Path]]:
        """Group daily notes by year and week"""
        weekly_notes = {}
        
        for date_str, file_path in daily_notes.items():
            year_week = self.get_week_number(date_str)
            
            if year_week not in weekly_notes:
                weekly_notes[year_week] = {}
            
            weekly_notes[year_week][date_str] = file_path
        
        return weekly_notes
    
    def get_week_identifier(self, year: int, week: int) -> str:
        """Get standard week identifier string (e.g., '2024-W50')"""
        return f"{year}-W{week:02d}"
    
    def get_missing_weeks(self, project_name: str) -> List[Tuple[int, int]]:
        """Get list of weeks that don't have a timeline entry yet"""
        # Find all daily notes for this project
        daily_notes = self.find_project_daily_notes(project_name)
        
        if not daily_notes:
            print(f"No daily notes found for project: {project_name}")
            return []
        
        # Group by week
        weekly_notes = self.group_notes_by_week(daily_notes)
        
        # Create project timeline folder if needed
        project_path = self.config.projects_path / project_name
        timeline_path = project_path / "timeline"
        timeline_path.mkdir(parents=True, exist_ok=True)
        
        # Check which weeks are missing timeline entries
        missing_weeks = []
        for year_week in weekly_notes.keys():
            year, week = year_week
            week_file = timeline_path / f"{self.get_week_identifier(year, week)}.md"
            
            if not week_file.exists():
                missing_weeks.append(year_week)
        
        # Sort chronologically
        missing_weeks.sort()
        return missing_weeks
    
    def read_daily_note_content(self, note_path: Path) -> Dict[str, str]:
        """Read and parse daily note content"""
        if not note_path.exists():
            return {
                "date": note_path.stem.split('_')[0],
                "summary": "Note file not found",
                "completed": "",
                "blockers": "",
                "next_steps": "",
                "thoughts": ""
            }
        
        with open(note_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract sections using regex
        sections = {
            "date": note_path.stem.split('_')[0],
            "summary": "",
            "completed": "",
            "blockers": "",
            "next_steps": "",
            "thoughts": ""
        }
        
        # Extract summary
        summary_match = re.search(r'## 📋 Summary\s+(.*?)(?=##|\Z)', content, re.DOTALL)
        if summary_match:
            sections["summary"] = summary_match.group(1).strip()
        
        # Extract completed
        completed_match = re.search(r'## ✅ Completed Today\s+(.*?)(?=##|\Z)', content, re.DOTALL)
        if completed_match:
            sections["completed"] = completed_match.group(1).strip()
        
        # Extract blockers
        blockers_match = re.search(r'## 🚧 In Progress / Blockers\s+(.*?)(?=##|\Z)', content, re.DOTALL)
        if blockers_match:
            sections["blockers"] = blockers_match.group(1).strip()
        
        # Extract next steps
        next_steps_match = re.search(r'## 📝 Next Steps\s+(.*?)(?=##|\Z)', content, re.DOTALL)
        if next_steps_match:
            sections["next_steps"] = next_steps_match.group(1).strip()
        
        # Extract thoughts
        thoughts_match = re.search(r'## 💭 Thoughts & Ideas\s+(.*?)(?=##|\Z|---)', content, re.DOTALL)
        if thoughts_match:
            sections["thoughts"] = thoughts_match.group(1).strip()
        
        return sections
    
    def create_system_prompt(self) -> str:
        """Create system prompt for weekly summary generation"""
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
"""

    def generate_weekly_summary(self, project_name: str, year: int, week: int, 
                               notes_content: List[Dict[str, str]]) -> Dict[str, str]:
        """Generate weekly summary from daily notes using LLM"""
        # Format daily notes for the prompt
        formatted_notes = []
        
        for note in notes_content:
            formatted_note = f"Date: {note['date']}\n"
            formatted_note += f"Summary: {note['summary']}\n"
            formatted_note += f"Completed: {note['completed']}\n"
            formatted_note += f"Blockers: {note['blockers']}\n"
            formatted_note += f"Next Steps: {note['next_steps']}\n"
            formatted_note += f"Thoughts: {note['thoughts']}\n\n"
            formatted_notes.append(formatted_note)
        
        notes_text = "\n---\n".join(formatted_notes)
        
        # Create prompt
        week_range = self.get_week_range(year, week)
        week_start = week_range[0].strftime('%Y-%m-%d')
        week_end = week_range[1].strftime('%Y-%m-%d')
        
        user_prompt = f"""
Project: {project_name}
Week: {year}-W{week:02d} ({week_start} to {week_end})

Daily Notes:
{notes_text}

Please analyze these daily notes and generate a weekly summary.
"""

        try:
            # Tokens for a 5 daily notes week summarazitaion are around 2500 (Input + Output)
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.create_system_prompt()},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            content = response.choices[0].message.content
            
            # Parse the JSON response
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return self._parse_fallback_response(content)
                
        except Exception as e:
            print(f"Error generating weekly summary: {e}")
            return self._create_error_response()
    
    def _parse_fallback_response(self, content: str) -> Dict[str, str]:
        """Fallback parser if JSON response fails"""
        sections = {
            'week_summary': 'Error parsing summary',
            'accomplishments': '- Error parsing accomplishments',
            'insights': '- Error parsing insights',
            'blockers': '- Error parsing blockers',
            'next_focus': 'Error parsing next focus'
        }
        
        # Simple regex-based extraction as fallback
        patterns = {
            'week_summary': r'week_summary["\s:]+([^"]+)',
            'accomplishments': r'accomplishments["\s:]+([^"]+)',
            'insights': r'insights["\s:]+([^"]+)',
            'blockers': r'blockers["\s:]+([^"]+)',
            'next_focus': r'next_focus["\s:]+([^"]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                sections[key] = match.group(1).strip()
        
        return sections
    
    def _create_error_response(self) -> Dict[str, str]:
        """Create error response for weekly summary"""
        return {
            'week_summary': 'Error generating weekly summary',
            'accomplishments': '- Could not process daily notes',
            'insights': '- Error occurred during processing',
            'blockers': '- Please review daily notes manually',
            'next_focus': 'Manual review needed'
        }
        
    def get_weekly_template(self) -> str:
        """Get template for weekly summary"""
        return """---
    tags: [timeline, weekly-summary, project/{project_name}]
    week: {week_id}
    date_range: {date_range}
    ---

    # Week {week_id}: {date_range} - {project_name}

    ## 📊 Week Summary
    {week_summary}

    ## 🎯 Key Accomplishments
    {accomplishments}

    ## 💭 Insights & Thoughts
    {insights}

    ## 🚧 Progress Indicators
    {blockers}

    ## 📝 Next Week Focus
    {next_focus}

    {completed_todos_section}

    ## 📄 Daily Notes References
    {daily_notes_links}
    """

    def find_completed_todos(self, project_name: str) -> List[Dict]:
        """Find completed todos in project's todo list"""
        todo_path = self.config.projects_path / project_name / "todo.md"
        if not todo_path.exists():
            return []
            
        completed_todos = []
        try:
            with open(todo_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Find completed todos (checked boxes)
            # Match pattern: - [x] 🔴|🟠|🟢 Task text _context_ *[[source_note|Source]]*
            todo_pattern = r'- \[x\] (🔴|🟠|🟢)? ?(.*?)( _.*?_)? \*\[\[(.*?)\|(Source)\]\]\* *\n'
            
            # Try alternative patterns if needed
            if not re.search(todo_pattern, content):
                todo_pattern = r'- \[x\] (🔴|🟠|🟢)? ?(.*?)( _.*?_)? \*\[\[(.*?)\]\]\* *\n'
                
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
                    
                completed_todos.append({
                    "task": task_text,
                    "priority": priority,
                    "context": context,
                    "source": source
                })
                
            return completed_todos
        except Exception as e:
            print(f"Error finding completed todos: {e}")
            return []

    def clean_completed_todos(self, project_name: str) -> int:
        """Remove completed todos from todo list and return count of removed items"""
        todo_path = self.config.projects_path / project_name / "todo.md"
        if not todo_path.exists():
            return 0
            
        try:
            with open(todo_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Replace completed todos with empty string
            # - [x] 🔴|🟠|🟢 Task text _context_ *[[source_note|Source]]*
            new_content = re.sub(r'- \[x\] (🔴|🟠|🟢)? ?.*?( _.*?_)? \*\[\[.*?\|Source\]\]\* *\n', '', content)
            
            # Try alternative pattern if needed
            if new_content == content:
                new_content = re.sub(r'- \[x\] (🔴|🟠|🟢)? ?.*?( _.*?_)? \*\[\[.*?\]\]\* *\n', '', content)
            
            # Count removed items
            removed_count = content.count('- [x]')
            
            # Write updated content
            with open(todo_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return removed_count
        except Exception as e:
            print(f"Error cleaning completed todos: {e}")
            return 0

    def create_weekly_summary_file(self, project_name: str, year: int, week: int) -> Optional[Path]:
        """Create weekly summary file for a project"""
        # Find daily notes for this project
        daily_notes = self.find_project_daily_notes(project_name)
        
        if not daily_notes:
            print(f"No daily notes found for project: {project_name}")
            return None
        
        # Group by week
        weekly_notes = self.group_notes_by_week(daily_notes)
        
        # Check if there are notes for this week
        year_week = (year, week)
        if year_week not in weekly_notes:
            print(f"No daily notes found for week {year}-W{week:02d} in project {project_name}")
            return None
        
        # Get week dates
        week_range = self.get_week_range(year, week)
        week_start = week_range[0].strftime('%Y-%m-%d')
        week_end = week_range[1].strftime('%Y-%m-%d')
        week_id = self.get_week_identifier(year, week)
        
        # Read content of daily notes
        notes_content = []
        for date_str, file_path in sorted(weekly_notes[year_week].items()):
            note_content = self.read_daily_note_content(file_path)
            notes_content.append(note_content)
        
        # Generate weekly summary
        summary = self.generate_weekly_summary(project_name, year, week, notes_content)
        
        # Find and clean completed todos
        completed_todos = self.find_completed_todos(project_name)
        cleaned_count = self.clean_completed_todos(project_name)
        
        # Create completed todos section if tracking is enabled
        completed_todos_section = ""
        if self.config.track_completed_todos and completed_todos:
            completed_todos_section = "## ✅ Completed Tasks\n"
            for todo in completed_todos:
                priority_indicator = ""
                if todo.get("priority") == "high":
                    priority_indicator = "🔴 "
                elif todo.get("priority") == "medium":
                    priority_indicator = "🟠 "
                elif todo.get("priority") == "low":
                    priority_indicator = "🟢 "
                    
                task_text = todo["task"]
                context = todo.get("context", "")
                source = todo.get("source", "")
                
                completed_todos_section += f"- {priority_indicator}{task_text}"
                if context:
                    completed_todos_section += f" _{context}_"
                completed_todos_section += f" *[[{source}|Source]]* \n"
            completed_todos_section += "\n"
        
        # Create links to daily notes
        daily_links = []
        for date_str, file_path in sorted(weekly_notes[year_week].items()):
            note_file_name = os.path.basename(file_path)
            daily_links.append(f"- [{date_str}: Daily Log]({note_file_name})")
        
        daily_notes_links = "\n".join(daily_links)
        
        # Fill template
        content = self.get_weekly_template().format(
            week_id=week_id,
            date_range=f"{week_start} to {week_end}",
            project_name=project_name,
            week_summary=summary['week_summary'],
            accomplishments=summary['accomplishments'],
            insights=summary['insights'],
            blockers=summary['blockers'],
            next_focus=summary['next_focus'],
            completed_todos_section=completed_todos_section,
            daily_notes_links=daily_notes_links
        )
        
        # Create project timeline folder if needed
        project_path = self.config.projects_path / project_name
        timeline_path = project_path / "timeline"
        timeline_path.mkdir(parents=True, exist_ok=True)
        
        # Write file
        week_file = timeline_path / f"{week_id}.md"
        with open(week_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Created weekly summary: {week_file.name}")
        if cleaned_count > 0:
            print(f"Cleaned {cleaned_count} completed todos from todo list")
        
        return week_file

    def update_timeline_index(self, project_name: str) -> Optional[Path]:
        """Update master timeline index file"""
        project_path = self.config.projects_path / project_name
        timeline_path = project_path / "timeline"
        
        if not timeline_path.exists():
            print(f"No timeline folder found for project: {project_name}")
            return None
        
        # Find all weekly summary files
        weekly_files = []
        for file_path in timeline_path.glob('*.md'):
            if file_path.name != 'timeline_index.md':
                match = re.match(r'(\d{4})-W(\d{2})\.md', file_path.name)
                if match:
                    year = int(match.group(1))
                    week = int(match.group(2))
                    week_range = self.get_week_range(year, week)
                    week_start = week_range[0].strftime('%Y-%m-%d')
                    week_end = week_range[1].strftime('%Y-%m-%d')
                    
                    # Get week summary from file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    summary = ""
                    summary_match = re.search(r'## 📊 Week Summary\s+(.*?)(?=##|\Z)', content, re.DOTALL)
                    if summary_match:
                        # Get the entire summary, cleaned up
                        summary = summary_match.group(1).strip()
                        # Remove extra whitespace and normalize line breaks
                        summary = ' '.join(summary.split())
                    
                    weekly_files.append({
                        'file': file_path,
                        'year': year,
                        'week': week,
                        'date_range': f"{week_start} to {week_end}",
                        'summary': summary
                    })
        
        if not weekly_files:
            print(f"No weekly summaries found for project: {project_name}")
            return None
        
        # Sort by year and week (newest first)
        weekly_files.sort(key=lambda x: (x['year'], x['week']), reverse=True)
        
        # Create index content
        index_content = f"# {project_name} Timeline\n\n"
        
        # Recent weeks section
        index_content += "## Recent Weeks\n"
        for entry in weekly_files[:12]:  # Show last 12 weeks
            week_id = self.get_week_identifier(entry['year'], entry['week'])
            index_content += f"- [{week_id}: {entry['date_range']}]({week_id}.md) - {entry['summary']}\n"
        
        # All weeks section
        if len(weekly_files) > 12:
            index_content += "\n## All Weeks\n"
            # Group by year
            years = {}
            for entry in weekly_files:
                if entry['year'] not in years:
                    years[entry['year']] = []
                years[entry['year']].append(entry)
            
            # Sort years in descending order
            for year in sorted(years.keys(), reverse=True):
                index_content += f"\n### {year}\n"
                for entry in sorted(years[year], key=lambda x: x['week'], reverse=True):
                    week_id = self.get_week_identifier(entry['year'], entry['week'])
                    index_content += f"- [Week {entry['week']:02d}: {entry['date_range']}]({week_id}.md)\n"
        
        # Write index file
        index_file = timeline_path / "timeline_index.md"
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        print(f"Updated timeline index for project: {project_name}")
        return index_file
    
    def generate_missing_weeks(self, project_name: str) -> int:
        """Generate timeline entries for all missing weeks"""
        missing_weeks = self.get_missing_weeks(project_name)
        
        if not missing_weeks:
            print(f"No missing timeline entries for project: {project_name}")
            return 0
        
        print(f"Generating {len(missing_weeks)} missing timeline entries for project: {project_name}")
        
        count = 0
        for year_week in missing_weeks:
            year, week = year_week
            week_id = self.get_week_identifier(year, week)
            print(f"Processing {week_id}...")
            
            if self.create_weekly_summary_file(project_name, year, week):
                count += 1
        
        if count > 0:
            self.update_timeline_index(project_name)
        
        return count
    
    def process_all_projects(self) -> Dict[str, int]:
        """Process all available projects"""
        available_projects = self.config.get_available_projects()
        
        if not available_projects:
            print("No projects found")
            return {}
        
        results = {}
        
        for project in available_projects:
            print(f"\nProcessing project: {project}")
            count = self.generate_missing_weeks(project)
            results[project] = count
        
        return results