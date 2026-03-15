"""
Audio-to-Obsidian Daily Notes Generator

Usage:
    python main.py                    # Interactive mode
    python main.py --batch            # Process all files once
    python main.py --file audio.mp3   # Process single file
    python main.py --todos audio.mp3  # Extract todos only from file
"""

import argparse
import os
import sys
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from src.daily_notes_processor import DailyNotesProcessor


class DesktopConsoleApp:
    """Console UI for the desktop processor."""

    def __init__(self, processor: DailyNotesProcessor):
        self.processor = processor

    def run(self):
        print("Daily Notes Processor - Interactive Mode")
        print("=" * 50)

        while True:
            print("\nChoose an option:")
            print("1. Scan for new audio files")
            print("2. Record new voice note")
            print("3. Generate timeline")
            print("4. Show current settings")
            print("5. Extract todos from audio")
            print("6. Exit")

            choice = input("\nEnter choice (1-6): ").strip()

            if choice == "1":
                self._scan_audio_files()
            elif choice == "2":
                self._record_voice_note_menu()
            elif choice == "3":
                self._generate_timeline()
            elif choice == "4":
                self._show_settings()
            elif choice == "5":
                self._extract_todos_from_audio()
            elif choice == "6":
                print("Goodbye!")
                self.processor.cleanup()
                break
            else:
                print("Invalid choice. Please try again.")

    def _extract_todos_from_audio(self):
        print("\nExtract Todos from Audio")
        print("-" * 30)

        if not self.processor.config.audio_input_path.exists():
            print(f"Audio inbox not found: {self.processor.config.audio_input_path}")
            return

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
                print(f"Please enter a number between 1 and {len(audio_files)}")
        except ValueError:
            print("Please enter a valid number")

    def _record_voice_note_menu(self):
        print("\nVoice Note Options")
        print("-" * 30)
        print("1. Record new voice note")
        print("2. Configure audio device")
        print("3. Return to main menu")

        choice = input("\nEnter choice (1-3): ").strip()

        if choice == "1":
            self._record_voice_note()
        elif choice == "2":
            self._configure_audio_device()
        elif choice == "3":
            return
        else:
            print("Invalid choice.")

    def _scan_audio_files(self):
        print(f"\nScanning: {self.processor.config.audio_input_path}")

        if not self.processor.config.audio_input_path.exists():
            print(f"Audio inbox not found: {self.processor.config.audio_input_path}")
            return

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
        print("s. Select specific file")
        print("c. Cancel")

        choice = input("\nEnter choice (a/t/s/c): ").strip().lower()

        if choice == "a":
            success_count = 0
            for audio_path in audio_files:
                if self.processor.process_audio_file(audio_path):
                    success_count += 1
            print(f"\nProcessed {success_count}/{len(audio_files)} files as daily notes!")

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

    def _record_voice_note(self):
        recorder = self.processor.audio_recorder

        print("\nRecording Voice Note")
        print("-" * 30)

        if not recorder.test_default_device():
            print("Default audio device not available.")
            device_id = recorder.select_device()
            if device_id is None:
                print("No working audio device found!")
                return
            recorder.selected_device_id = device_id

        print(f"\nReady to record to: {self.processor.config.audio_input_path}")
        input("Press ENTER when ready to start recording...")

        audio_path = recorder.record_and_save(self.processor.config.audio_input_path)
        if not audio_path:
            print("Recording failed!")
            return

        print(f"\nRecording saved: {audio_path.name}")
        response = input("Process this recording now? (y/n): ").strip().lower()

        if response in ["y", "yes"]:
            print(f"\nProcessing {audio_path.name}...")
            if self.processor.process_audio_file(audio_path):
                print("Voice note processed successfully!")
            else:
                print("Processing failed!")
        else:
            print("Recording saved to inbox for later processing.")

    def _configure_audio_device(self):
        recorder = self.processor.audio_recorder

        print("\nAudio Device Configuration")
        print("-" * 30)

        if recorder.selected_device_id is None:
            default_device = recorder.get_default_input_device()
            current_device = (
                f"System Default ({default_device['name']})" if default_device else "System Default"
            )
        else:
            devices = recorder.get_available_devices()
            current_device = next(
                (name for device_id, name, _ in devices if device_id == recorder.selected_device_id),
                "Unknown",
            )

        print(f"Current device: {current_device}")

        response = input("\nChange audio device? (y/n): ").strip().lower()
        if response not in ["y", "yes"]:
            return

        device_id = recorder.select_device()
        if device_id is not None:
            print("\nTesting device...")
            if recorder.test_device(device_id):
                recorder.selected_device_id = device_id
                print("Device configured successfully!")
            else:
                print("Device test failed!")
        else:
            recorder.selected_device_id = None
            print("Using system default device")

    def _show_settings(self):
        print("\nCurrent Settings")
        print("-" * 30)
        for key, value in self.processor.get_settings_summary().items():
            print(f"{key}: {value}")

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


def main():
    parser = argparse.ArgumentParser(description="Audio to Obsidian Daily Notes")
    parser.add_argument("--batch", action="store_true", help="Process all audio files and exit")
    parser.add_argument("--file", type=str, help="Process specific audio file as daily note")
    parser.add_argument("--todos", type=str, help="Process specific file for todos only")
    parser.add_argument(
        "--timeline",
        action="store_true",
        help="Generate missing weekly summaries and exit",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Config file name (in config directory)",
    )

    args = parser.parse_args()

    try:
        processor = DailyNotesProcessor(args.config)

        if args.file:
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"Error: File not found: {file_path}")
                sys.exit(1)

            if file_path.parent != processor.config.audio_input_path:
                inbox_path = processor.config.audio_input_path / file_path.name
                file_path.rename(inbox_path)
                file_path = inbox_path
                print(f"Moved {args.file} to inbox")

            success = processor.process_audio_file(file_path)
            sys.exit(0 if success else 1)

        if args.todos:
            file_path = Path(args.todos)
            if not file_path.exists():
                print(f"Error: File not found: {file_path}")
                sys.exit(1)

            if file_path.parent != processor.config.audio_input_path:
                inbox_path = processor.config.audio_input_path / file_path.name
                file_path.rename(inbox_path)
                file_path = inbox_path
                print(f"Moved {args.todos} to inbox")

            success = processor.process_audio_for_todos(file_path)
            sys.exit(0 if success else 1)

        if args.batch:
            results = processor.process_all_audio()
            sys.exit(0 if results["failed"] == 0 else 1)

        if args.timeline:
            print("Generating missing weekly summaries...")
            results = processor.generate_timelines_for_all_projects()

            total = sum(results.values())
            if total > 0:
                print(f"Generated {total} timeline entries across {len(results)} projects")
                for project, count in results.items():
                    if count > 0:
                        print(f"  - {project}: {count} entries")
            else:
                print("No missing weekly summaries found")

            sys.exit(0)

        DesktopConsoleApp(processor).run()

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
