import yaml
from pathlib import Path
from typing import Dict, List


class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.script_dir = Path(__file__).parent.parent
        self.config_dir = self.script_dir / "config"
        self.main_dir = self.script_dir.parent

        self.config_data = self._load_or_create_config()

        # Load keys quietly; validation reports only the ones that matter.
        self.openai_api_key = self._load_api_key("openai")
        self.assembly_api_key = self._load_api_key("assembly")
        self.deepseek_api_key = self._load_api_key("deepseek")

    def _load_api_key(self, service: str) -> str:
        """Load an API key from config/<service>_api_key.txt if present."""
        api_key_file = self.config_dir / f"{service}_api_key.txt"

        if not api_key_file.exists():
            return ""

        try:
            with open(api_key_file, "r", encoding="utf-8") as file_handle:
                api_key = file_handle.read().strip()

            if not api_key or api_key == f"your_{service}_api_key_here":
                return ""

            return api_key
        except Exception as error:
            print(f"Error reading {service.title()} API key: {error}")
            return ""

    def _load_or_create_config(self) -> Dict:
        """Load an existing config or create a default one."""
        self.config_dir.mkdir(exist_ok=True)
        config_file = self.config_dir / self.config_path

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as file_handle:
                return yaml.safe_load(file_handle)

        default_config = self._get_default_config()
        with open(config_file, "w", encoding="utf-8") as file_handle:
            yaml.dump(default_config, file_handle, default_flow_style=False, indent=2)
        print(f"Created default configuration at {config_file}")
        return default_config

    def _get_default_config(self) -> Dict:
        """Generate a default configuration."""
        return {
            "project": {
                "name": "MyCurrentProject",
                "vault_path": "../ObsidianVault",
                "daily_notes_path": "../Daily",
                "projects_path": "../Projects",
            },
            "audio": {
                "input_folder": "AudioInbox",
                "supported_formats": [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"],
                "max_duration_seconds": 1800,
                "min_duration_seconds": 5,
                "delete_after_processing": True,
            },
            "processing": {
                "whisper_model": "base",
                "llm_provider": "openai",
                "model": "gpt-4.1-mini",
                "weekly_summary_model": "gpt-4.1",
                "temperature": 0.3,
                "max_tokens": 2000,
                "audio_model": "whisper",
                "batch_size": 16,
                "beam_size": 5,
                "language_code": "en",
                "compute_type": "float32",
                "cpu_threads": 4,
                "num_workers": 2,
                "assembly_model": "slam",
                "track_completed_todos": True,
            },
            "output": {
                "date_format": "%Y-%m-%d",
                "include_audio_filename": True,
                "include_processing_timestamp": True,
                "save_transcript": True,
                "transcript_folder": "transcripts",
            },
            "debug": {
                "save_llm_conversations": False,
                "debug_folder": "debug_logs",
            },
        }

    def get_available_projects(self) -> List[str]:
        """Get a sorted list of project folders."""
        available_projects = []

        if not self.projects_path.exists():
            print(f"Projects path not found: {self.projects_path}")
            return []

        for item in self.projects_path.iterdir():
            if item.is_dir() and item.name != "Daily Notes":
                available_projects.append(item.name)

        return sorted(available_projects)

    @property
    def project_name(self) -> str:
        return self.config_data["project"]["name"]

    @property
    def vault_path(self) -> Path:
        return self.main_dir / self.config_data["project"]["vault_path"]

    @property
    def daily_notes_path(self) -> Path:
        return self.main_dir / self.config_data["project"]["daily_notes_path"]

    @property
    def projects_path(self) -> Path:
        return self.main_dir / self.config_data["project"]["projects_path"]

    @property
    def audio_input_path(self) -> Path:
        return self.script_dir / self.config_data["audio"]["input_folder"]

    @property
    def supported_formats(self) -> List[str]:
        return self.config_data["audio"]["supported_formats"]

    @property
    def max_duration(self) -> int:
        return self.config_data["audio"]["max_duration_seconds"]

    @property
    def min_duration(self) -> int:
        return self.config_data["audio"]["min_duration_seconds"]

    @property
    def delete_after_processing(self) -> bool:
        return self.config_data["audio"]["delete_after_processing"]

    @property
    def whisper_model(self) -> str:
        return self.config_data["processing"]["whisper_model"]

    @property
    def audio_model(self) -> str:
        return self.config_data["processing"].get("audio_model", "whisper")

    @property
    def batch_size(self) -> int:
        return self.config_data["processing"].get("batch_size", 16)

    @property
    def beam_size(self) -> int:
        return self.config_data["processing"].get("beam_size", 5)

    @property
    def track_completed_todos(self) -> bool:
        return self.config_data["processing"].get("track_completed_todos", True)

    @property
    def language_code(self) -> str:
        return self.config_data["processing"].get("language_code", "en")

    @property
    def llm_provider(self) -> str:
        return self.config_data["processing"].get("llm_provider", "openai")

    @property
    def model(self) -> str:
        return self.config_data["processing"].get("model", "gpt-4o-mini")

    @property
    def weekly_summary_model(self) -> str:
        return self.config_data["processing"].get("weekly_summary_model", self.model)

    @property
    def temperature(self) -> float:
        return self.config_data["processing"]["temperature"]

    @property
    def max_tokens(self) -> int:
        return self.config_data["processing"]["max_tokens"]

    @property
    def save_transcript(self) -> bool:
        return self.config_data["output"].get("save_transcript", False)

    @property
    def transcript_folder(self) -> str:
        return self.config_data["output"].get("transcript_folder", "transcripts")

    @property
    def compute_type(self) -> str:
        return self.config_data["processing"].get("compute_type", "float32")

    @property
    def cpu_threads(self) -> int:
        return self.config_data["processing"].get("cpu_threads", 4)

    @property
    def num_workers(self) -> int:
        return self.config_data["processing"].get("num_workers", 2)

    @property
    def assembly_model(self) -> str:
        return self.config_data["processing"].get("assembly_model", "slam")

    @property
    def debug_llm(self) -> bool:
        return self.config_data.get("debug", {}).get("save_llm_conversations", False)

    @property
    def debug_folder(self) -> str:
        return self.config_data.get("debug", {}).get("debug_folder", "debug_logs")

    def validate_config(self, raise_on_error: bool = False) -> bool:
        """Validate the active configuration and required credentials."""
        errors = []

        if self.llm_provider not in {"openai", "deepseek"}:
            errors.append(
                f"Unsupported llm_provider '{self.llm_provider}'. Use 'openai' or 'deepseek'."
            )

        if self.llm_provider == "openai" and not self.openai_api_key:
            errors.append("OpenAI API key missing for llm_provider='openai'.")

        if self.llm_provider == "deepseek" and not self.deepseek_api_key:
            errors.append("DeepSeek API key missing for llm_provider='deepseek'.")

        if self.audio_model not in {"whisper", "assembly"}:
            errors.append(
                f"Unsupported audio_model '{self.audio_model}'. Use 'whisper' or 'assembly'."
            )

        if self.audio_model == "assembly" and not self.assembly_api_key:
            errors.append("AssemblyAI API key missing for audio_model='assembly'.")

        for key in ("vault_path", "daily_notes_path", "projects_path"):
            if not self.config_data.get("project", {}).get(key):
                errors.append(f"Missing project.{key} in config.")

        if not self.supported_formats:
            errors.append("audio.supported_formats must contain at least one file extension.")

        if errors:
            message = "Configuration issues:\n- " + "\n- ".join(errors)
            if raise_on_error:
                raise ValueError(message)
            print(message)
            return False

        return True

    def print_config_summary(self):
        """Print configuration summary."""
        print("\nConfiguration Summary:")
        print(f"  Project: {self.project_name}")
        print(f"  Vault: {self.vault_path}")
        print(f"  Daily Notes: {self.daily_notes_path}")
        print(f"  Audio Inbox: {self.audio_input_path}")
        print(f"  Whisper Model: {self.whisper_model}")
        print(f"  GPT Model: {self.model}")
        print(f"  Delete Audio After Processing: {self.delete_after_processing}")
