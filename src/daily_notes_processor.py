from pathlib import Path
from typing import List
import sys
import re
from datetime import datetime

from .config import Config
from .audio_processor import AudioProcessor
from .note_generator import NoteGenerator
from .timeline_generator import TimelineGenerator
from .audio_recorder import AudioRecorder
from .todo_extractor import TodoExtractor

class DailyNotesProcessor:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the daily notes processor"""
        self.config = Config(config_path)
        self.audio_processor = AudioProcessor(self.config)
        self.audio_recorder = AudioRecorder()
        self.note_generator = NoteGenerator(
            self.config,
            self.config.openai_api_key,
            self.config.config_data['processing']['gpt_model'],
            self.config.config_data['processing']['temperature']
        )
        self.timeline_generator = TimelineGenerator(
            self.config,
            self.config.openai_api_key,
            self.config.weekly_summary_model,  # Use the weekly summary model
            self.config.config_data['processing']['temperature']
        )
        
        # Initialize TodoExtractor
        self.todo_extractor = TodoExtractor(
            self.config,
            self.note_generator,
            self.audio_processor
        )
        
        # Create necessary folders
        self._setup_folders()
        
    def _setup_folders(self):
        """Create necessary folder structure"""
        folders = [
            self.config.audio_input_path,
            self.config.daily_notes_path,
            self.config.projects_path
        ]
        
        # Add transcript folder if saving transcripts is enabled
        if self.config.save_transcript:
            folders.append(self.config.daily_notes_path / self.config.transcript_folder)
            
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            
        print(f"Setup complete. Drop audio files in: {self.config.audio_input_path}")
    
    def find_audio_files(self) -> List[Path]:
        """Find unprocessed audio files in inbox"""
        supported_formats = self.config.config_data['audio']['supported_formats']
        audio_files = []
        
        for format_ext in supported_formats:
            audio_files.extend(self.config.audio_input_path.glob(f"*{format_ext}"))
            
        return sorted(audio_files)
    
    def process_audio_file(self, audio_path: Path) -> bool:
        """Process single audio file into daily note"""
        try:
            print(f"\n{'='*50}")
            print(f"Processing: {audio_path.name}")
            print(f"{'='*50}")
            
            # Extract date from filename if possible
            date_str = self.todo_extractor.extract_date_from_filename(audio_path.name)
            if date_str:
                print(f"Date extracted from filename: {date_str}")
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')
                print(f"Using current date: {date_str}")
            
            # 1. Transcribe audio
            transcript_data = self.audio_processor.transcribe(audio_path)
            print(f"Transcription completed ({len(transcript_data['text'])} chars)")
            
            # 2. Get available projects
            available_projects = self.config.get_available_projects()
            # print(f"Available projects: {', '.join(available_projects)}")
            
            # 3. Generate daily note with project detection and extracted date
            note_path = self.note_generator.create_daily_note(
                transcript_data=transcript_data,
                available_projects=available_projects,
                audio_filename=audio_path.name,
                output_path=self.config.daily_notes_path,
                date_str=date_str
            )
            
            # 4. Delete audio file if configured
            if self.config.config_data['audio']['delete_after_processing']:
                success = self.audio_processor.delete_audio_file(audio_path)
                if not success:
                    print(f"⚠ Warning: Could not delete {audio_path.name}")
            
            print(f"✅ Success! Note: {note_path.name}")
            return True
            
        except Exception as e:
            print(f"❌ Error processing {audio_path.name}: {e}")
            return False
    
    def process_audio_for_todos(self, audio_path: Path) -> bool:
        """Process audio file for todo extraction only"""
        return self.todo_extractor.process_audio_for_todos(audio_path)
    
    def process_all_audio(self) -> dict:
        """Process all audio files in inbox"""
        audio_files = self.find_audio_files()
        
        if not audio_files:
            print("No audio files found in inbox")
            return {'processed': 0, 'failed': 0}
        
        results = {'processed': 0, 'failed': 0}
        
        for audio_file in audio_files:
            if self.process_audio_file(audio_file):
                results['processed'] += 1
            else:
                results['failed'] += 1
        
        print(f"\n{'='*50}")
        print(f"BATCH COMPLETE")
        print(f"Processed: {results['processed']}")
        print(f"Failed: {results['failed']}")
        print(f"{'='*50}")
        
        return results
        
    def run_interactive(self):
        """Interactive mode for processing daily notes"""
        print("🎯 Daily Notes Processor - Interactive Mode")
        print("=" * 50)
        
        while True:
            print("\nChoose an option:")
            print("1. 📁 Scan for new audio files")
            print("2. 🎤 Record new voice note")
            print("3. 📅 Generate timeline")
            print("4. 📋 Show current settings")
            print("5. ✅ Extract todos from audio")
            print("6. 🚪 Exit")
            
            choice = input("\nEnter choice (1-6): ").strip()
            
            if choice == '1':
                self._scan_audio_files()
            elif choice == '2':
                self._record_voice_note_menu()
            elif choice == '3':
                self._generate_timeline()
            elif choice == '4':
                self._show_settings()
            elif choice == '5':
                self._extract_todos_from_audio()
            elif choice == '6':
                print("👋 Goodbye!")
                self.audio_recorder.cleanup()
                break
            else:
                print("❌ Invalid choice. Please try again.")

    def _extract_todos_from_audio(self):
        """Menu for extracting todos from audio without creating daily notes"""
        print(f"\n✅ Extract Todos from Audio")
        print("-" * 30)
        
        # Check if path exists
        if not self.config.audio_input_path.exists():
            print(f"❌ Audio inbox not found: {self.config.audio_input_path}")
            return
        
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
                print(f"❌ Please enter a number between 1 and {len(audio_files)}")
        except ValueError:
            print("❌ Please enter a valid number")

    def _record_voice_note_menu(self):
        """Show recording menu with configuration option"""
        print("\n🎤 Voice Note Options")
        print("-" * 30)
        print("1. Record new voice note")
        print("2. Configure audio device")
        print("3. Return to main menu")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == '1':
            self._record_voice_note()
        elif choice == '2':
            self._configure_audio_device()
        elif choice == '3':
            return
        else:
            print("❌ Invalid choice.")
            return
    
    def _scan_audio_files(self):
        """Scan and process audio files from inbox"""
        print(f"\n🔍 Scanning: {self.config.audio_input_path}")
        
        # Check if path exists
        if not self.config.audio_input_path.exists():
            print(f"❌ Audio inbox not found: {self.config.audio_input_path}")
            return
        
        # Get audio files
        audio_files = self.find_audio_files()
        
        if not audio_files:
            print("📭 No audio files found.")
            return
        
        print(f"📄 Found {len(audio_files)} audio file(s):")
        for i, file_path in enumerate(audio_files, 1):
            print(f"  {i}. {file_path.name}")
        
        # Options for processing
        print("\nOptions:")
        print("a. Process all files as daily notes")
        print("t. Process all files for todos only")
        print("s. Select specific file")
        print("c. Cancel")
        
        choice = input("\nEnter choice (a/t/s/c): ").strip().lower()
        
        if choice == 'a':
            # Process all files
            success_count = 0
            for audio_path in audio_files:
                if self.process_audio_file(audio_path):
                    success_count += 1
            
            print(f"\n✅ Processed {success_count}/{len(audio_files)} files as daily notes!")
        
        elif choice == 't':
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
    
    def _record_voice_note(self):
        """Record a new voice note"""
        print(f"\n🎤 Recording Voice Note")
        print("-" * 30)
        
        # Test default device first
        if not self.audio_recorder.test_default_device():
            print("⚠️  Default audio device not available.")
            device_id = self.audio_recorder.select_device()
            if device_id is None:
                print("❌ No working audio device found!")
                return
            self.audio_recorder.selected_device_id = device_id
        
        # Record audio
        print(f"\n🎙️  Ready to record to: {self.config.audio_input_path}")
        input("Press ENTER when ready to start recording...")
        
        audio_path = self.audio_recorder.record_and_save(
            self.config.audio_input_path
        )
        
        if not audio_path:
            print("❌ Recording failed!")
            return
        
        # Ask if user wants to process immediately
        print(f"\n✅ Recording saved: {audio_path.name}")
        response = input("Process this recording now? (y/n): ").strip().lower()
        
        if response in ['y', 'yes']:
            print(f"\n🔄 Processing {audio_path.name}...")
            if self.process_audio_file(audio_path):
                print("✅ Voice note processed successfully!")
            else:
                print("❌ Processing failed!")
        else:
            print("💾 Recording saved to inbox for later processing.")

    def _configure_audio_device(self):
        """Configure audio input device"""
        print(f"\n⚙️  Audio Device Configuration")
        print("-" * 30)
        
        # Show current device
        if self.audio_recorder.selected_device_id is None:
            default_device = self.audio_recorder.get_default_input_device()
            current_device = f"System Default ({default_device['name']})" if default_device else "System Default"
        else:
            devices = self.audio_recorder.get_available_devices()
            current_device = next((name for id, name, _ in devices if id == self.audio_recorder.selected_device_id), 
                                "Unknown")
        
        print(f"Current device: {current_device}")
        
        # Ask if user wants to change
        response = input("\nChange audio device? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            return
        
        device_id = self.audio_recorder.select_device()
        
        if device_id is not None:
            print(f"\n🔧 Testing device...")
            if self.audio_recorder.test_device(device_id):
                self.audio_recorder.selected_device_id = device_id
                print("✅ Device configured successfully!")
            else:
                print("❌ Device test failed!")
        else:
            self.audio_recorder.selected_device_id = None
            print("✅ Using system default device")

    def _show_settings(self):
        """Show current configuration"""
        print(f"\n📋 Current Settings")
        print("-" * 30)
        print(f"Projects Path: {self.config.projects_path}")
        print(f"Audio Inbox: {self.config.audio_input_path}")
        print(f"Daily Notes: {self.config.daily_notes_path}")
        print(f"Delete after processing: {self.config.delete_after_processing}")
        print(f"Save transcripts: {self.config.save_transcript}")
        if self.config.save_transcript:
            print(f"Transcript folder: {self.config.transcript_folder}")
        
        # Transcription settings
        print(f"Transcription model: {self.config.audio_model}")
        if self.config.audio_model == 'whisper':
            print(f"  Whisper model: {self.config.whisper_model}")
            print(f"  Compute type: {self.config.compute_type}")
            print(f"  CPU threads: {self.config.cpu_threads}")
            print(f"  Workers: {self.config.num_workers}")
        elif self.config.audio_model == 'assembly':
            print(f"  AssemblyAI model: {self.config.assembly_model}")
        
        # LLM settings
        print(f"GPT Model: {self.config.gpt_model}")
        print(f"Weekly Summary Model: {self.config.weekly_summary_model}")

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

def main():
    """Main entry point"""
    try:
        processor = DailyNotesProcessor()
        processor.run_interactive()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
