from openai import OpenAI
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import re
from typing import List
from .todo_manager import TodoManager

class NoteGenerator:
    def __init__(self, config, api_key: str, model: str = "gpt-4o", temperature: float = 0.3):
        """Initialize OpenAI client"""
        self.config = config
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.todo_manager = TodoManager(config, api_key, model, temperature)
        
    def get_daily_note_template(self) -> str:
        """Get the daily note template"""
        return """---
date: {date}
project: {project_name}
tags: [daily, work-log, project/{project_name}]
---

# Daily Log: {date}

## 📋 Summary
{summary}

## ✅ Completed Today
{completed}

## 🚧 In Progress / Blockers
{blockers}

## 📝 Next Steps
{next_steps}

## 💭 Thoughts & Ideas
{thoughts}

{transcript_link}
---
*Generated from audio transcript on {timestamp}*
"""

    def create_system_prompt(self, available_projects: List[str]) -> str:
        """Create the system prompt for GPT with project detection"""
        projects_list = ", ".join(available_projects) if available_projects else "No projects available"
        
        return f"""You are a professional work journal assistant. Your task is to convert audio transcripts of daily work logs into structured, clear daily notes.

Given a transcript of someone describing their workday, extract and organize the information into these specific categories:

**Project**: Identify which project the person is working on from this list: [{projects_list}]
**Summary**: A max 150 words overview of the day's work
**Completed**: Specific tasks, features, or goals that were finished
**In Progress/Blockers**: Current work and any obstacles encountered
**Next Steps**: Plans for upcoming work
**Thoughts & Ideas**: Insights, learnings, or creative ideas mentioned

Guidelines:
- Use bullet points for lists
- Be specific and actionable
- If information for a section isn't mentioned, write "None mentioned"
- Maintain the speaker's tone but make it more structured and improve readibility
- Extract concrete details like feature names, technologies, metrics when mentioned
- If the transcript is unclear, note this appropriately
- For project identification: Look for mentions like "Today I worked on X", "X project", etc. Use fuzzy matching if the transcription seems imprecise (e.g., "Palienci" might be "Saliency")
- If no clear project is mentioned or none match, use "Unknown"

Format your response as a JSON object with keys: project, summary, completed, blockers, next_steps, thoughts
Each key should contain a string value with markdown formatting (bullet points using -).
If a section has no relevant content, use an empty string.
"""

    def _fix_bullet_points(self, text: str) -> str:
        """Fix bullet points by replacing \n- with proper line breaks"""
        # Replace \n- with actual line breaks followed by dashes
        if text:
            text = text.replace('\\n-', '\n-')
            # Also fix potential issue with \n followed by space followed by dash
            text = text.replace('\\n -', '\n-')
        return text

    def generate_note_content(self, transcript: str, available_projects: List[str]) -> Dict[str, str]:
        """Generate structured note content from transcript using GPT"""
        
        user_prompt = f"""
Available Projects: {', '.join(available_projects)}

Audio Transcript:
{transcript}

Please analyze this transcript and extract the structured information as requested. Pay special attention to identifying which project is being discussed, even if the transcription might be slightly inaccurate.
"""

        try:
            # A note request has around 1000 tokens (input and output) for an audio of 2:30 mins

            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.create_system_prompt(available_projects)},
                    {"role": "user", "content": user_prompt}
                ]
            )
            content = response.choices[0].message.content
            
            # Try to parse JSON response
            import json
            try:
                parsed_content = json.loads(content)
                # Fix any remaining \n- in bullet points
                for key in parsed_content:
                    if isinstance(parsed_content[key], str):
                        parsed_content[key] = self._fix_bullet_points(parsed_content[key])
                return parsed_content
            except json.JSONDecodeError:
                # Fallback: extract content manually if JSON parsing fails
                return self._parse_fallback_response(content, available_projects)
                
        except Exception as e:
            print(f"Error generating note content: {e}")
            return self._create_error_response(transcript)
    
    def _parse_fallback_response(self, content: str, available_projects: List[str]) -> Dict[str, str]:
        """Fallback parser if JSON response fails"""
        sections = {
            'project': 'Unknown',
            'summary': 'Could not parse summary',
            'completed': '- Could not parse completed tasks',
            'blockers': '- Could not parse blockers',
            'next_steps': '- Could not parse next steps',
            'thoughts': '- Could not parse thoughts'
        }
        
        # Simple regex-based extraction as fallback
        patterns = {
            'project': r'project["\s:]+([^"]+)',
            'summary': r'summary["\s:]+([^"]+)',
            'completed': r'completed["\s:]+([^"]+)',
            'blockers': r'blockers["\s:]+([^"]+)',
            'next_steps': r'next_steps["\s:]+([^"]+)',
            'thoughts': r'thoughts["\s:]+([^"]+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                extracted_text = match.group(1).strip()
                sections[key] = self._fix_bullet_points(extracted_text)
        
        return sections
    
    def _create_error_response(self, transcript: str) -> Dict[str, str]:
        """Create error response with original transcript"""
        return {
            'project': 'Unknown',
            'summary': 'Error processing transcript - manual review needed',
            'completed': '- See raw transcript below',
            'blockers': '- Processing error occurred',
            'next_steps': '- Review and manually edit this note',
            'thoughts': f'Raw transcript:\n{transcript}'
        }
    def _save_transcript(self, transcript_text: str, date_str: str, project_name: str, output_path: Path) -> Path:
        """Save transcript to file and return path"""
        # Create transcript folder
        transcript_folder = output_path / self.config.transcript_folder
        transcript_folder.mkdir(parents=True, exist_ok=True)
        
        # Create transcript file
        transcript_filename = f"{date_str}_{project_name}_transcript.md"
        transcript_path = transcript_folder / transcript_filename
        
        # Handle existing file
        if transcript_path.exists():
            timestamp_suffix = datetime.now().strftime('%H%M%S')
            transcript_path = transcript_folder / f"{date_str}_{project_name}_transcript_{timestamp_suffix}.md"
        
        # Write transcript with frontmatter
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(f"---\ndate: {date_str}\nproject: {project_name}\ntags: [transcript, project/{project_name}]\n---\n\n")
            f.write(f"# Transcript: {date_str} - {project_name}\n\n")
            f.write(transcript_text)
        
        print(f"Saved transcript: {transcript_path}")
        return transcript_path
    
    def create_daily_note(self, 
                        transcript_data: Dict[str, Any], 
                        available_projects: List[str],
                        audio_filename: str,
                        output_path: Path,
                        date_str: str = None) -> Path:
        """Create complete daily note file"""
        
        # Generate content from transcript
        content = self.generate_note_content(transcript_data['text'], available_projects)
        
        # Extract detected project
        detected_project = content.get('project', 'Unknown')
        
        # Prepare template variables
        now = datetime.now()
        if date_str is None:
            date_str = now.strftime('%Y-%m-%d')
        
        template_vars = {
            'date': date_str,
            'project_name': detected_project,
            'audio_filename': audio_filename,
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            'summary': content['summary'],
            'completed': content['completed'],
            'blockers': content['blockers'],
            'next_steps': content['next_steps'],
            'thoughts': content['thoughts'],
            'transcript_link': ""  # Default empty
        }
        
        # Save transcript if enabled
        if self.config.save_transcript:
            transcript_path = self._save_transcript(
                transcript_data['text'],
                date_str,
                detected_project,
                output_path
            )
            # Create relative path for the link
            relative_path = transcript_path.name if transcript_path.parent == output_path else f"{self.config.transcript_folder}/{transcript_path.name}"
            template_vars['transcript_link'] = f"## 📝 Full Transcript\n[View complete transcript]({relative_path})\n"
        
        # Fill template
        note_content = self.get_daily_note_template().format(**template_vars)
        
        # Create output file
        daily_note_path = output_path / f"{date_str}_{detected_project}.md"
        
        # Handle existing file
        if daily_note_path.exists():
            timestamp_suffix = now.strftime('%H%M%S')
            daily_note_path = output_path / f"{date_str}_{detected_project}_{timestamp_suffix}.md"
            print(f"Daily note exists, creating: {daily_note_path.name}")
        
        # Write file
        with open(daily_note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)
            
        print(f"Created daily note for project '{detected_project}': {daily_note_path}")

        # Extract and add todo items
        print("Checking for todo items in transcript...")
        todo_items = self.todo_manager.extract_todos(transcript_data['text'], detected_project)

        if todo_items:
            print(f"Found {len(todo_items)} todo items.")
            self.todo_manager.add_todos_to_project(detected_project, todo_items, date_str)
        else:
            print("No todo items found in transcript.")

        return daily_note_path