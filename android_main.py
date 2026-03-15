"""
Daily Notes Processor - Android Version
"""

import sys
from datetime import datetime
from pathlib import Path

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir / "src"))

from src.android_audio_processor import AndroidAudioProcessor
from src.config import Config
from src.note_generator import NoteGenerator
from src.timeline_generator import TimelineGenerator
from src.todo_extractor import TodoExtractor


class AndroidNotesProcessor:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the Android processor core."""
        self.config = Config(config_path)
        self.config.validate_config(raise_on_error=True)

        self.audio_processor = AndroidAudioProcessor(self.config)

        self.note_generator = NoteGenerator(
            self.config,
            model=self.config.model,
            temperature=self.config.temperature,
        )

        self.timeline_generator = TimelineGenerator(
            self.config,
            model=self.config.weekly_summary_model,
            temperature=self.config.temperature,
        )

        self.todo_extractor = TodoExtractor(
            self.config,
            self.note_generator,
            self.audio_processor,
        )

        self._setup_folders()

    def _setup_folders(self):
        folders = [
            self.config.audio_input_path,
            self.config.daily_notes_path,
            self.config.projects_path,
        ]

        if self.config.save_transcript:
            folders.append(self.config.daily_notes_path / self.config.transcript_folder)

        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)

    def find_audio_files(self):
        """Find audio files in inbox."""
        audio_files = []
        for format_ext in self.config.supported_formats:
            audio_files.extend(self.config.audio_input_path.glob(f"*{format_ext}"))
        return sorted(audio_files)

    def get_available_projects(self):
        return self.config.get_available_projects()

    def get_settings_summary(self):
        settings = {
            "Projects Path": self.config.projects_path,
            "Audio Inbox": self.config.audio_input_path,
            "Daily Notes": self.config.daily_notes_path,
            "Delete after processing": self.config.delete_after_processing,
            "Save transcripts": self.config.save_transcript,
            "Available Projects": ", ".join(self.get_available_projects()) or "None",
            "LLM Provider": self.config.llm_provider,
            "Model": self.config.model,
            "Weekly Summary Model": self.config.weekly_summary_model,
            "Transcription model": self.config.audio_model,
        }

        if self.config.save_transcript:
            settings["Transcript folder"] = self.config.transcript_folder

        if self.config.audio_model == "assembly":
            settings["AssemblyAI model"] = self.config.assembly_model
        else:
            settings["Whisper model"] = self.config.whisper_model

        return settings

    def generate_timelines_for_all_projects(self):
        return self.timeline_generator.process_all_projects()

    def generate_timeline_for_project(self, project_name: str):
        return self.timeline_generator.generate_missing_weeks(project_name)

    def process_audio_file(self, audio_path):
        """Process a single audio file."""
        try:
            print(f"\n{'=' * 40}")
            print(f"Processing: {audio_path.name}")
            print(f"{'=' * 40}")

            date_str = self.todo_extractor.extract_date_from_filename(audio_path.name)
            if date_str:
                print(f"Date extracted from filename: {date_str}")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                print(f"Using current date: {date_str}")

            transcript_data = self.audio_processor.transcribe(audio_path)
            print(f"Transcription completed ({len(transcript_data['text'])} chars)")

            available_projects = self.config.get_available_projects()
            print(f"Available projects: {', '.join(available_projects)}")

            note_path = self.note_generator.create_daily_note(
                transcript_data=transcript_data,
                available_projects=available_projects,
                audio_filename=audio_path.name,
                output_path=self.config.daily_notes_path,
                date_str=date_str,
            )

            if self.config.delete_after_processing:
                success = self.audio_processor.delete_audio_file(audio_path)
                if not success:
                    print(f"Warning: Could not delete {audio_path.name}")

            print(f"Success! Note: {note_path.name}")
            return True

        except Exception as error:
            print(f"Error processing {audio_path.name}: {error}")
            return False

    def process_audio_for_todos(self, audio_path):
        """Process an audio file to extract todos only."""
        return self.todo_extractor.process_audio_for_todos(audio_path)


class AndroidConsoleApp:
    """Console UI for Android/Pydroid."""

    def __init__(self, processor: AndroidNotesProcessor):
        self.processor = processor

    def run(self):
        self._print_header()

        while True:
            print("\nMenu Options:")
            print("1. Process audio files")
            print("2. Generate timeline entries")
            print("3. Extract todos from audio")
            print("4. Show current settings")
            print("5. Exit")

            try:
                choice = input("\nEnter choice (1-5): ").strip()

                if choice == "1":
                    self._process_audio_files()
                elif choice == "2":
                    self._generate_timeline()
                elif choice == "3":
                    self._extract_todos_from_audio()
                elif choice == "4":
                    self._show_settings()
                elif choice == "5":
                    print("\nGoodbye!")
                    break
                else:
                    print("Invalid choice. Please try again.")
            except Exception as error:
                print(f"Error: {error}")

    def _print_header(self):
        print("\n" + "=" * 50)
        print("Daily Notes Processor - Android Edition")
        print("=" * 50)
        print("\nSetup:")
        print("1. Record audio with your phone's recorder app")
        print("2. Save it to:", self.processor.config.audio_input_path)
        print("3. Process it with this app")
        print("4. Configuration files are in:", self.processor.config.config_dir)
        print("=" * 50)

    def _extract_todos_from_audio(self):
        print("\nExtract Todos from Audio")
        print("-" * 30)

        audio_files = self.processor.find_audio_files()
        if not audio_files:
            print("No audio files found.")
            return

        print(f"Found {len(audio_files)} audio file(s):")
        for index, file_path in enumerate(audio_files, start=1):
            print(f"  {index}. {file_path.name}")

        try:
            file_choice = int(input(f"\nEnter file number (1-{len(audio_files)}) or 0 to cancel: "))
            if file_choice == 0:
                print("Extraction cancelled.")
                return

            if 1 <= file_choice <= len(audio_files):
                audio_path = audio_files[file_choice - 1]
                success = self.processor.process_audio_for_todos(audio_path)
                if success:
                    print("Todo extraction completed successfully!")
                else:
                    print("Todo extraction failed!")
            else:
                print(f"Please enter a number between 0 and {len(audio_files)}")
        except ValueError:
            print("Please enter a valid number")

    def _process_audio_files(self):
        print("\nLooking for audio files...")

        audio_files = self.processor.find_audio_files()
        if not audio_files:
            print("No audio files found.")
            return

        print(f"Found {len(audio_files)} audio file(s):")
        for index, file_path in enumerate(audio_files, start=1):
            print(f"  {index}. {file_path.name}")

        print("\nOptions:")
        print("a. Process all files as daily notes")
        print("t. Process all files for todos only")
        print("s. Select a specific file")
        print("c. Cancel")

        choice = input("Enter choice (a/t/s/c): ").strip().lower()

        if choice == "a":
            success_count = 0
            for audio_path in audio_files:
                if self.processor.process_audio_file(audio_path):
                    success_count += 1
            print(f"\nProcessed {success_count}/{len(audio_files)} files successfully!")

        elif choice == "t":
            success_count = 0
            for audio_path in audio_files:
                if self.processor.process_audio_for_todos(audio_path):
                    success_count += 1
            print(f"\nProcessed {success_count}/{len(audio_files)} files for todos!")

        elif choice == "s":
            try:
                file_choice = int(input(f"Enter file number (1-{len(audio_files)}): "))
                if 1 <= file_choice <= len(audio_files):
                    audio_path = audio_files[file_choice - 1]

                    print("\nProcess as:")
                    print("1. Daily note")
                    print("2. Todos only")

                    process_choice = input("Enter choice (1/2): ").strip()
                    if process_choice == "1":
                        self.processor.process_audio_file(audio_path)
                    elif process_choice == "2":
                        self.processor.process_audio_for_todos(audio_path)
                    else:
                        print("Invalid choice.")
                else:
                    print(f"Please enter a number between 1 and {len(audio_files)}")
            except ValueError:
                print("Please enter a valid number")

        elif choice == "c":
            print("Processing cancelled.")
        else:
            print("Invalid choice.")

    def _generate_timeline(self):
        print("\nTimeline Generator")
        print("-" * 30)

        available_projects = self.processor.get_available_projects()
        if not available_projects:
            print("No projects found. Add projects to your projects folder first.")
            return

        print(f"Available projects: {', '.join(available_projects)}")
        print("\nOptions:")
        print("1. Process all projects")
        print("2. Select a specific project")
        print("3. Cancel")

        choice = input("\nEnter choice (1-3): ").strip()
        if choice == "1":
            print("\nProcessing all projects...")
            results = self.processor.generate_timelines_for_all_projects()
            total = sum(results.values())
            print(f"\nGenerated {total} timeline entries across {len(results)} projects")
            for project, count in results.items():
                print(f"  - {project}: {count} entries")

        elif choice == "2":
            print("\nSelect a project:")
            for index, project in enumerate(available_projects, start=1):
                print(f"{index}. {project}")

            while True:
                try:
                    project_choice = int(
                        input(f"\nEnter project number (1-{len(available_projects)}): ")
                    )
                    if 1 <= project_choice <= len(available_projects):
                        selected_project = available_projects[project_choice - 1]
                        break
                    print(f"Please enter a number between 1 and {len(available_projects)}")
                except ValueError:
                    print("Please enter a valid number")

            print(f"\nProcessing project: {selected_project}...")
            count = self.processor.generate_timeline_for_project(selected_project)
            if count > 0:
                print(f"\nGenerated {count} timeline entries for {selected_project}")
            else:
                print(f"\nNo new timeline entries needed for {selected_project}")

        elif choice == "3":
            print("Timeline generation cancelled.")
        else:
            print("Invalid choice.")

    def _show_settings(self):
        print("\nCurrent Settings")
        print("-" * 30)
        for key, value in self.processor.get_settings_summary().items():
            print(f"{key}: {value}")


def main():
    try:
        processor = AndroidNotesProcessor()
        AndroidConsoleApp(processor).run()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
