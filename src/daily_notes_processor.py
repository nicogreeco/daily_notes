from datetime import datetime
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from .audio_processor import AudioProcessor
from .config import Config
from .note_generator import NoteGenerator
from .timeline_generator import TimelineGenerator
from .todo_extractor import TodoExtractor

if TYPE_CHECKING:
    from .audio_recorder import AudioRecorder


class DailyNotesProcessor:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the desktop daily notes processor."""
        self.config = Config(config_path)
        self.config.validate_config(raise_on_error=True)

        self.audio_processor = AudioProcessor(self.config)
        self._audio_recorder = None

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

    @property
    def audio_recorder(self) -> "AudioRecorder":
        """Create the recorder only when recording is actually used."""
        if self._audio_recorder is None:
            from .audio_recorder import AudioRecorder
            self._audio_recorder = AudioRecorder()
        return self._audio_recorder

    def _setup_folders(self):
        """Create the folder structure needed by the app."""
        folders = [
            self.config.audio_input_path,
            self.config.daily_notes_path,
            self.config.projects_path,
        ]

        if self.config.save_transcript:
            folders.append(self.config.daily_notes_path / self.config.transcript_folder)

        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)

        print(f"Setup complete. Drop audio files in: {self.config.audio_input_path}")

    def cleanup(self):
        """Release optional resources."""
        if self._audio_recorder is not None:
            self._audio_recorder.cleanup()

    def find_audio_files(self) -> List[Path]:
        """Find unprocessed audio files in the inbox."""
        audio_files = []

        for format_ext in self.config.supported_formats:
            audio_files.extend(self.config.audio_input_path.glob(f"*{format_ext}"))

        return sorted(audio_files)

    def get_available_projects(self) -> List[str]:
        return self.config.get_available_projects()

    def get_settings_summary(self) -> Dict[str, object]:
        """Return a UI-friendly settings snapshot."""
        settings = {
            "Projects Path": self.config.projects_path,
            "Audio Inbox": self.config.audio_input_path,
            "Daily Notes": self.config.daily_notes_path,
            "Delete after processing": self.config.delete_after_processing,
            "Save transcripts": self.config.save_transcript,
            "LLM Provider": self.config.llm_provider,
            "Model": self.config.model,
            "Weekly Summary Model": self.config.weekly_summary_model,
            "Transcription model": self.config.audio_model,
        }

        if self.config.save_transcript:
            settings["Transcript folder"] = self.config.transcript_folder

        if self.config.audio_model == "whisper":
            settings["Whisper model"] = self.config.whisper_model
            settings["Compute type"] = self.config.compute_type
            settings["CPU threads"] = self.config.cpu_threads
            settings["Workers"] = self.config.num_workers
        elif self.config.audio_model == "assembly":
            settings["AssemblyAI model"] = self.config.assembly_model

        return settings

    def generate_timelines_for_all_projects(self) -> Dict[str, int]:
        return self.timeline_generator.process_all_projects()

    def generate_timeline_for_project(self, project_name: str) -> int:
        return self.timeline_generator.generate_missing_weeks(project_name)

    def process_audio_file(self, audio_path: Path) -> bool:
        """Process a single audio file into a daily note."""
        try:
            print(f"\n{'=' * 50}")
            print(f"Processing: {audio_path.name}")
            print(f"{'=' * 50}")

            date_str = self.todo_extractor.extract_date_from_filename(audio_path.name)
            if date_str:
                print(f"Date extracted from filename: {date_str}")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                print(f"Using current date: {date_str}")

            transcript_data = self.audio_processor.transcribe(audio_path)
            print(f"Transcription completed ({len(transcript_data['text'])} chars)")

            available_projects = self.config.get_available_projects()

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

    def process_audio_for_todos(self, audio_path: Path) -> bool:
        """Process an audio file for todo extraction only."""
        return self.todo_extractor.process_audio_for_todos(audio_path)

    def process_all_audio(self) -> dict:
        """Process all audio files currently in the inbox."""
        audio_files = self.find_audio_files()

        if not audio_files:
            print("No audio files found in inbox")
            return {"processed": 0, "failed": 0}

        results = {"processed": 0, "failed": 0}

        for audio_file in audio_files:
            if self.process_audio_file(audio_file):
                results["processed"] += 1
            else:
                results["failed"] += 1

        print(f"\n{'=' * 50}")
        print("BATCH COMPLETE")
        print(f"Processed: {results['processed']}")
        print(f"Failed: {results['failed']}")
        print(f"{'=' * 50}")

        return results
