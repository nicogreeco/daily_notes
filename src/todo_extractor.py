"""
Todo Extractor Module
Handles extraction of todos from audio files without creating daily notes
"""
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

class TodoExtractor:
    def __init__(self, config, note_generator, audio_processor):
        """Initialize the todo extractor"""
        self.config = config
        self.note_generator = note_generator
        self.audio_processor = audio_processor
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """Extract date from filename if it follows the 'Daily_Log_dd-mm-yyyy' pattern"""
        # Try the primary pattern "Daily_Log_dd-mm-yyyy"
        pattern = r'Daily_Log_(\d{2})-(\d{2})-(\d{4})'
        match = re.search(pattern, filename)
        
        if match:
            day, month, year = match.groups()
            try:
                # Create a datetime object to validate the date
                date_obj = datetime(int(year), int(month), int(day))
                # Return in the YYYY-MM-DD format
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # Invalid date
                return None
        
        # Try alternative patterns as fallbacks
        # Format: YYYY-MM-DD anywhere in the filename
        alt_pattern = r'(\d{4})-(\d{2})-(\d{2})'
        match = re.search(alt_pattern, filename)
        if match:
            year, month, day = match.groups()
            try:
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                return None
        
        # Format: DD-MM-YYYY anywhere in the filename
        alt_pattern2 = r'(\d{2})-(\d{2})-(\d{4})'
        match = re.search(alt_pattern2, filename)
        if match:
            day, month, year = match.groups()
            try:
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                return None
                
        return None
    
    def process_audio_for_todos(self, audio_path: Path) -> bool:
        """Process an audio file to extract todos only"""
        try:
            print(f"\nProcessing for todos: {audio_path.name}")
            
            # Use current date for todos
            date_str = datetime.now().strftime('%Y-%m-%d')
            
            # Transcribe audio
            transcript_data = self.audio_processor.transcribe(audio_path)
            print(f"✓ Transcription completed ({len(transcript_data['text'])} chars)")
            
            # Get available projects
            available_projects = self.config.get_available_projects()
            
            # Generate content from transcript to extract project
            content = self.note_generator.generate_note_content(transcript_data['text'], available_projects)
            
            # Extract detected project
            project_name = content.get('project', 'Unknown')
            print(f"📌 Detected project: {project_name}")
            
            # Save transcript with generic name
            transcript_folder = self.config.daily_notes_path / self.config.transcript_folder
            transcript_folder.mkdir(parents=True, exist_ok=True)
            
            transcript_filename = f"{date_str}_TodoExtract_{project_name}.md"
            transcript_path = transcript_folder / transcript_filename
            
            # Handle existing file
            if transcript_path.exists():
                timestamp_suffix = datetime.now().strftime('%H%M%S')
                transcript_path = transcript_folder / f"{date_str}_TodoExtract_{project_name}_{timestamp_suffix}.md"
            
            # Write transcript with frontmatter
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(f"---\ndate: {date_str}\nproject: {project_name}\ntags: [transcript, todo-extract, project/{project_name}]\n---\n\n")
                f.write(f"# Todo Extract: {date_str} - {project_name}\n\n")
                f.write(transcript_data['text'])
            
            print(f"✓ Saved transcript: {transcript_path.name}")
            
            # Extract todos
            todo_items = self.note_generator.todo_manager.extract_todos(
                transcript_data['text'], 
                project_name
            )
            
            if todo_items:
                print(f"Found {len(todo_items)} todo items for project '{project_name}'")
                self.note_generator.todo_manager.add_todos_to_project(
                    project_name, 
                    todo_items, 
                    date_str
                )
                print(f"✅ Added {len(todo_items)} todos to project '{project_name}'")
            else:
                print("❌ No todo items found in transcript.")
                
            # Delete audio file if configured
            if self.config.delete_after_processing:
                success = self.audio_processor.delete_audio_file(audio_path)
                if not success:
                    print(f"⚠ Warning: Could not delete {audio_path.name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing {audio_path.name}: {e}")
            return False