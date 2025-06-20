"""
Daily Notes Processor - Android Version
Simplified version for Pydroid 3 on Android devices

This version:
- Processes existing audio files from the inbox folder
- Uses AssemblyAI for transcription
- Provides a simple menu interface
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import re

# Add src directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir / 'src'))

from src.config import Config
from src.android_audio_processor import AndroidAudioProcessor
from src.note_generator import NoteGenerator
from src.timeline_generator import TimelineGenerator

class AndroidNotesProcessor:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the processor for Android"""
        self.config = Config(config_path)
        self.audio_processor = AndroidAudioProcessor(self.config)
        
        # Update these initializations to match the new structure
        self.note_generator = NoteGenerator(
            self.config,
            model=self.config.gpt_model,
            temperature=self.config.config_data['processing']['temperature']
        )
        self.timeline_generator = TimelineGenerator(
            self.config,
            model=self.config.weekly_summary_model,
            temperature=self.config.config_data['processing']['temperature']
        )
        
        # Print app header
        self._print_header()
    
    def _print_header(self):
        """Print app header"""
        print("\n" + "=" * 50)
        print("📱 Daily Notes Processor - Android Edition")
        print("=" * 50)
        print("\nSetup:")
        print("1. Record audio with your phone's recorder app")
        print("2. Save it to:", self.config.audio_input_path)
        print("3. Process it with this app")
        print("4. Configuration files are in:", self.config.config_dir)
        print("=" * 50)
    
    def extract_date_from_filename(self, filename: str):
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
    
    def find_audio_files(self):
        """Find audio files in inbox"""
        supported_formats = self.config.supported_formats
        audio_files = []
        
        for format_ext in supported_formats:
            audio_files.extend(self.config.audio_input_path.glob(f"*{format_ext}"))
            
        return sorted(audio_files)
    
    def process_audio_file(self, audio_path):
        """Process a single audio file"""
        try:
            print(f"\n{'='*40}")
            print(f"Processing: {audio_path.name}")
            print(f"{'='*40}")
            
            # Extract date from filename if possible
            date_str = self.extract_date_from_filename(audio_path.name)
            if date_str:
                print(f"Date extracted from filename: {date_str}")
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')
                print(f"Using current date: {date_str}")
            
            # Transcribe audio
            transcript_data = self.audio_processor.transcribe(audio_path)
            print(f"✓ Transcription completed ({len(transcript_data['text'])} chars)")
            
            # Get available projects
            available_projects = self.config.get_available_projects()
            print(f"Available projects: {', '.join(available_projects)}")
            
            # Generate daily note
            note_path = self.note_generator.create_daily_note(
                transcript_data=transcript_data,
                available_projects=available_projects,
                audio_filename=audio_path.name,
                output_path=self.config.daily_notes_path,
                date_str=date_str
            )
            
            # Delete audio file if configured
            if self.config.delete_after_processing:
                success = self.audio_processor.delete_audio_file(audio_path)
                if not success:
                    print(f"⚠ Warning: Could not delete {audio_path.name}")
            
            print(f"✅ Success! Note: {note_path.name}")
            return True
            
        except Exception as e:
            print(f"❌ Error processing {audio_path.name}: {e}")
            return False
    
    def process_audio_for_todos(self, audio_path):
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
    
    def run_menu(self):
        """Show and process the main menu"""
        while True:
            print("\n📋 Menu Options:")
            print("1. Process audio files")
            print("2. Generate timeline entries")
            print("3. Extract todos from audio")
            print("4. Show current settings")
            print("5. Exit")
            
            try:
                choice = input("\nEnter choice (1-5): ").strip()
                
                if choice == '1':
                    self._process_audio_files()
                elif choice == '2':
                    self._generate_timeline()
                elif choice == '3':
                    self._extract_todos_from_audio()
                elif choice == '4':
                    self._show_settings()
                elif choice == '5':
                    print("\n👋 Goodbye!")
                    break
                else:
                    print("❌ Invalid choice. Please try again.")
            except Exception as e:
                print(f"Error: {e}")
    
    def _extract_todos_from_audio(self):
        """Extract todos from audio without creating daily notes"""
        print("\n✅ Extract Todos from Audio")
        print("-" * 30)
        
        # Get audio files
        audio_files = self.find_audio_files()
        
        if not audio_files:
            print("📭 No audio files found.")
            return
        
        print(f"📄 Found {len(audio_files)} audio file(s):")
        for i, file_path in enumerate(audio_files, 1):
            print(f"  {i}. {file_path.name}")
        
        # Ask which file to process
        try:
            file_choice = int(input(f"\nEnter file number (1-{len(audio_files)}) or 0 to cancel: "))
            if file_choice == 0:
                print("⏭️ Extraction cancelled.")
                return
                
            if 1 <= file_choice <= len(audio_files):
                audio_path = audio_files[file_choice - 1]
                success = self.process_audio_for_todos(audio_path)
                if success:
                    print("✅ Todo extraction completed successfully!")
                else:
                    print("❌ Todo extraction failed!")
            else:
                print(f"❌ Please enter a number between 0 and {len(audio_files)}")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _process_audio_files(self):
        """Process audio files from inbox"""
        print("\n🔍 Looking for audio files...")
        
        # Get audio files
        audio_files = self.find_audio_files()
        
        if not audio_files:
            print("📭 No audio files found.")
            return
        
        print(f"📄 Found {len(audio_files)} audio file(s):")
        for i, file_path in enumerate(audio_files, 1):
            print(f"  {i}. {file_path.name}")
        
        # Ask which file to process
        print("\nOptions:")
        print("a. Process all files as daily notes")
        print("t. Process all files for todos only")
        print("s. Select a specific file")
        print("c. Cancel")
        
        choice = input("Enter choice (a/t/s/c): ").strip().lower()
        
        if choice == 'a':
            # Process all files
            success_count = 0
            for audio_path in audio_files:
                if self.process_audio_file(audio_path):
                    success_count += 1
            
            print(f"\n✅ Processed {success_count}/{len(audio_files)} files successfully!")
            
        elif choice == 't':
            # Process all files for todos only
            success_count = 0
                        # Process all files for todos only
            success_count = 0
            for audio_path in audio_files:
                if self.process_audio_for_todos(audio_path):
                    success_count += 1
            
            print(f"\n✅ Processed {success_count}/{len(audio_files)} files for todos!")
            
        elif choice == 's':
            # Select specific file
            try:
                file_choice = int(input(f"Enter file number (1-{len(audio_files)}): "))
                if 1 <= file_choice <= len(audio_files):
                    audio_path = audio_files[file_choice - 1]
                    
                    # Ask for processing type
                    print("\nProcess as:")
                    print("1. Daily note")
                    print("2. Todos only")
                    
                    process_choice = input("Enter choice (1/2): ").strip()
                    
                    if process_choice == '1':
                        self.process_audio_file(audio_path)
                    elif process_choice == '2':
                        self.process_audio_for_todos(audio_path)
                    else:
                        print("❌ Invalid choice.")
                else:
                    print(f"❌ Please enter a number between 1 and {len(audio_files)}")
            except ValueError:
                print("❌ Please enter a valid number")
        
        elif choice == 'c':
            print("⏭️ Processing cancelled.")
            return
        else:
            print("❌ Invalid choice.")
    
    def _generate_timeline(self):
        """Generate timeline entries for projects"""
        print("\n📅 Timeline Generator")
        print("-" * 30)
        
        # Get available projects
        available_projects = self.config.get_available_projects()
        
        if not available_projects:
            print("❌ No projects found. Add projects to your projects folder first.")
            return
        
        print(f"Available projects: {', '.join(available_projects)}")
        print("\nOptions:")
        print("1. Process all projects")
        print("2. Select a specific project")
        print("3. Cancel")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == '1':
            print("\n🔄 Processing all projects...")
            results = self.timeline_generator.process_all_projects()
            
            total = sum(results.values())
            print(f"\n✅ Generated {total} timeline entries across {len(results)} projects")
            
            for project, count in results.items():
                print(f"  - {project}: {count} entries")
                
        elif choice == '2':
            # Select project
            print("\nSelect a project:")
            for i, project in enumerate(available_projects, 1):
                print(f"{i}. {project}")
                
            while True:
                try:
                    project_choice = int(input(f"\nEnter project number (1-{len(available_projects)}): "))
                    if 1 <= project_choice <= len(available_projects):
                        selected_project = available_projects[project_choice - 1]
                        break
                    else:
                        print(f"❌ Please enter a number between 1 and {len(available_projects)}")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            print(f"\n🔄 Processing project: {selected_project}...")
            count = self.timeline_generator.generate_missing_weeks(selected_project)
            
            if count > 0:
                print(f"\n✅ Generated {count} timeline entries for {selected_project}")
            else:
                print(f"\nℹ️ No new timeline entries needed for {selected_project}")
                
        elif choice == '3':
            print("⏭️ Timeline generation cancelled.")
            return
        else:
            print("❌ Invalid choice.")
    
    def _show_settings(self):
        """Show current configuration"""
        print(f"\n📋 Current Settings")
        print("-" * 30)
        print(f"Projects Path: {self.config.projects_path}")
        print(f"Audio Inbox: {self.config.audio_input_path}")
        print(f"Daily Notes: {self.config.daily_notes_path}")
        print(f"Delete after processing: {self.config.delete_after_processing}")
        print(f"Save transcript: {self.config.save_transcript}")
        if self.config.save_transcript:
            print(f"Transcript folder: {self.config.transcript_folder}")
        
        # Available projects
        available_projects = self.config.get_available_projects()
        print(f"Available Projects: {', '.join(available_projects) if available_projects else 'None'}")

def main():
    """Main entry point"""
    try:
        processor = AndroidNotesProcessor()
        processor.run_menu()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()