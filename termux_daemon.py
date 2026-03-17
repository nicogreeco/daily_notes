"""
Termux daemon for unattended audio ingestion on Android.

Recommended flow:
- Telegram delivers audio files into the configured inbox folder.
- This daemon waits for files to become stable before claiming them.
- Notes and todos are generated and written into the configured vault.
- FolderSync syncs the vault folder to OneDrive.
"""

import argparse
import copy
import json
import logging
import mimetypes
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import error, request

from src.android_audio_processor import AndroidAudioProcessor
from src.config import Config
from src.note_generator import NoteGenerator
from src.timeline_generator import TimelineGenerator
from src.todo_extractor import TodoExtractor


LOGGER = logging.getLogger("termux_daemon")


@dataclass
class QueueFolders:
    inbox: Path
    processing: Path
    archive: Path
    failed: Path


@dataclass
class ProcessResult:
    success: bool
    audio_path: Path
    note_path: Optional[Path] = None
    error: str = ""


@dataclass
class UserProfile:
    chat_id: str
    name: str
    input_folder: str
    vault_path: str
    daily_notes_path: str
    projects_path: str


@dataclass
class UserRuntime:
    profile: UserProfile
    processor: "TermuxProcessor"
    detector: "StableFileDetector"
    folders: QueueFolders


@dataclass
class DownloadedAudio:
    chat_id: str
    path: Path


class TermuxProcessor:
    """Minimal processor core for unattended Android/Termux usage."""

    def __init__(self, config: Config):
        self.config = config
        self.config.validate_config(raise_on_error=True)

        # The daemon archives processed files itself.
        self.config.config_data["audio"]["delete_after_processing"] = False

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

    def _setup_folders(self) -> None:
        folders = [
            self.config.audio_input_path,
            self.config.daily_notes_path,
            self.config.projects_path,
        ]

        if self.config.save_transcript:
            folders.append(self.config.daily_notes_path / self.config.transcript_folder)

        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)

    def process_audio_file(self, audio_path: Path) -> ProcessResult:
        LOGGER.info("Processing audio file: %s", audio_path.name)

        try:
            date_str = self.todo_extractor.extract_date_from_filename(audio_path.name)
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")

            transcript_data = self.audio_processor.transcribe(audio_path)
            available_projects = self.config.get_available_projects()

            note_path = self.note_generator.create_daily_note(
                transcript_data=transcript_data,
                available_projects=available_projects,
                audio_filename=audio_path.name,
                output_path=self.config.daily_notes_path,
                date_str=date_str,
            )

            LOGGER.info("Created note: %s", note_path.name)
            return ProcessResult(success=True, audio_path=audio_path, note_path=note_path)
        except Exception as error:  # pragma: no cover - runtime defensive logging
            LOGGER.exception("Failed to process %s: %s", audio_path.name, error)
            return ProcessResult(success=False, audio_path=audio_path, error=str(error))


class StableFileDetector:
    """Require a file to stay unchanged for a minimum duration before processing."""

    def __init__(self, stability_seconds: int):
        self.stability_seconds = stability_seconds
        self._observations: Dict[Path, Tuple[int, float, float]] = {}

    def is_stable(self, path: Path) -> bool:
        try:
            stat_result = path.stat()
        except FileNotFoundError:
            self._observations.pop(path, None)
            return False

        size = stat_result.st_size
        mtime = stat_result.st_mtime
        now = time.monotonic()
        previous = self._observations.get(path)

        if previous is None or previous[:2] != (size, mtime):
            self._observations[path] = (size, mtime, now)
            return False

        stable_since = previous[2]
        if now - stable_since < self.stability_seconds:
            return False

        return True

    def forget(self, path: Path) -> None:
        self._observations.pop(path, None)

    def mark_stable(self, path: Path) -> None:
        try:
            stat_result = path.stat()
        except FileNotFoundError:
            return

        self._observations[path] = (
            stat_result.st_size,
            stat_result.st_mtime,
            time.monotonic() - self.stability_seconds,
        )


class TelegramBotClient:
    API_ROOT = "https://api.telegram.org"

    def __init__(self, config_dir: Path, state_path: Path, allowed_formats: List[str]):
        self.config_dir = config_dir
        self.state_path = state_path
        self.allowed_formats = {suffix.lower() for suffix in allowed_formats}
        self.bot_token = self._read_secret("telegram_bot_token.txt")
        self.enabled = bool(self.bot_token)
        self.offset = self._load_offset()
        self.chat_targets: Dict[str, UserRuntime] = {}

        if self.enabled:
            LOGGER.info("Telegram bot intake enabled")
        else:
            LOGGER.info("Telegram bot intake disabled; missing telegram_bot_token.txt")

    def set_chat_targets(self, chat_targets: Dict[str, UserRuntime]) -> None:
        self.chat_targets = chat_targets
        if self.enabled and not self.chat_targets:
            LOGGER.info("Telegram bot discovery mode enabled; no chat mappings configured yet")

    def _read_secret(self, filename: str) -> str:
        path = self.config_dir / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _load_offset(self) -> int:
        if not self.state_path.exists():
            return 0

        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return int(payload.get("telegram_offset", 0))
        except Exception:
            return 0

    def _save_offset(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"telegram_offset": self.offset}
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _api_url(self, method: str) -> str:
        return f"{self.API_ROOT}/bot{self.bot_token}/{method}"

    def _file_url(self, file_path: str) -> str:
        return f"{self.API_ROOT}/file/bot{self.bot_token}/{file_path}"

    def _api_request(self, method: str, data: Optional[dict] = None) -> dict:
        encoded = None
        headers = {}
        if data is not None:
            encoded = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(self._api_url(method), data=encoded, headers=headers, method="POST")
        with request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {payload}")

        return payload["result"]

    def _multipart_request(
        self,
        method: str,
        fields: Dict[str, str],
        file_field: str,
        file_path: Path,
    ) -> dict:
        boundary = f"----DailyNotes{int(time.time() * 1000)}"
        body = bytearray()

        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
            )

        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        file_bytes = file_path.read_bytes()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        req = request.Request(
            self._api_url(method),
            data=bytes(body),
            headers=headers,
            method="POST",
        )

        with request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {payload}")

        return payload["result"]

    def send_message(self, text: str) -> None:
        raise NotImplementedError("Use send_message_to_chat")

    def send_message_to_chat(self, chat_id: str, text: str) -> None:
        if not self.enabled:
            return

        try:
            self._api_request(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": text[:4096],
                },
            )
        except Exception as error:  # pragma: no cover - network runtime logging
            LOGGER.warning("Could not send Telegram message: %s", error)

    def send_document(self, file_path: Path, caption: str = "") -> None:
        raise NotImplementedError("Use send_document_to_chat")

    def send_document_to_chat(self, chat_id: str, file_path: Path, caption: str = "") -> None:
        if not self.enabled or not file_path.exists():
            return

        try:
            self._multipart_request(
                "sendDocument",
                {
                    "chat_id": chat_id,
                    "caption": caption[:1024],
                },
                "document",
                file_path,
            )
        except Exception as error:  # pragma: no cover - network runtime logging
            LOGGER.warning("Could not send Telegram document %s: %s", file_path.name, error)

    def _sanitize_filename(self, filename: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in filename).strip()
        return safe or f"audio_{int(time.time())}"

    def _ensure_supported_suffix(self, filename: str, fallback_suffix: str = ".ogg") -> Optional[str]:
        path = Path(filename)
        suffix = path.suffix.lower()
        if suffix in self.allowed_formats:
            return filename
        if not suffix and fallback_suffix in self.allowed_formats:
            return f"{filename}{fallback_suffix}"
        return None

    def _download_file(self, inbox_path: Path, file_id: str, filename_hint: str) -> Optional[Path]:
        file_info = self._api_request("getFile", {"file_id": file_id})
        file_path = file_info["file_path"]

        safe_name = self._sanitize_filename(filename_hint)
        supported_name = self._ensure_supported_suffix(safe_name)
        if supported_name is None:
            LOGGER.info("Skipping unsupported Telegram file: %s", filename_hint)
            return None

        target = self._unique_path(inbox_path / supported_name)
        tmp_target = target.with_suffix(target.suffix + ".part")

        with request.urlopen(self._file_url(file_path), timeout=300) as response:
            tmp_target.write_bytes(response.read())

        tmp_target.replace(target)
        return target

    def _unique_path(self, target: Path) -> Path:
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = target.with_name(f"{stem}_{timestamp}{suffix}")
        counter = 1

        while candidate.exists():
            candidate = target.with_name(f"{stem}_{timestamp}_{counter}{suffix}")
            counter += 1

        return candidate

    def poll_and_download(self) -> List[DownloadedAudio]:
        if not self.enabled:
            return []

        downloaded: List[DownloadedAudio] = []

        try:
            updates = self._api_request(
                "getUpdates",
                {
                    "offset": self.offset + 1,
                    "timeout": 0,
                    "allowed_updates": ["message"],
                },
            )
        except Exception as error:  # pragma: no cover - network runtime logging
            LOGGER.warning("Telegram polling failed: %s", error)
            return []

        for update in updates:
            self.offset = max(self.offset, update["update_id"])
            message = update.get("message", {})
            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))

            runtime = self.chat_targets.get(chat_id)
            if runtime is None:
                LOGGER.warning(
                    "Telegram discovery/unmapped chat: chat_id=%s name=%s",
                    chat_id,
                    chat.get("title") or chat.get("username") or chat.get("first_name") or "unknown",
                )
                continue

            text = (message.get("text") or "").strip()
            if text == "/status":
                self.send_message_to_chat(
                    chat_id,
                    f"Daemon is running for {runtime.profile.name} and listening for audio files.",
                )
                continue

            candidate = self._extract_audio_message(message)
            if candidate is None:
                continue

            file_id, filename = candidate
            try:
                local_path = self._download_file(runtime.folders.inbox, file_id, filename)
                if local_path is None:
                    self.send_message_to_chat(chat_id, f"Skipped unsupported file type: {filename}")
                    continue

                downloaded.append(DownloadedAudio(chat_id=chat_id, path=local_path))
                LOGGER.info("Downloaded Telegram audio to %s", local_path.name)
                self.send_message_to_chat(
                    chat_id,
                    f"Received `{local_path.name}` and queued it for processing.",
                )
            except error.URLError as download_error:
                LOGGER.warning("Could not download Telegram file %s: %s", filename, download_error)
                self.send_message_to_chat(chat_id, f"Failed to download `{filename}`.")
            except Exception as download_error:
                LOGGER.warning("Could not save Telegram file %s: %s", filename, download_error)
                self.send_message_to_chat(chat_id, f"Failed to save `{filename}`.")

        self._save_offset()
        return downloaded

    def _extract_audio_message(self, message: dict) -> Optional[Tuple[str, str]]:
        voice = message.get("voice")
        if voice:
            return voice["file_id"], f"voice_{message['message_id']}.ogg"

        audio = message.get("audio")
        if audio:
            filename = audio.get("file_name") or f"audio_{message['message_id']}.mp3"
            return audio["file_id"], filename

        document = message.get("document")
        if document:
            filename = document.get("file_name") or f"document_{message['message_id']}"
            return document["file_id"], filename

        return None


class TermuxDaemon:
    def __init__(
        self,
        config_path: str,
        *,
        poll_interval: int,
        stability_seconds: int,
        timeline_day: Optional[str],
        timeline_hour: Optional[int],
    ):
        self.base_config_path = config_path
        self.base_config = Config(config_path)
        self.base_config.validate_config(raise_on_error=True)
        self.poll_interval = poll_interval
        self.stability_seconds = stability_seconds
        self.timeline_day = timeline_day.lower() if timeline_day else None
        self.timeline_hour = timeline_hour
        self.last_timeline_run: Optional[str] = None
        self.running = True
        self.users = self._build_user_runtimes()
        self.users_by_chat_id = {runtime.profile.chat_id: runtime for runtime in self.users}

        self.telegram = TelegramBotClient(
            self.base_config.config_dir,
            Path("logs") / "termux_daemon_state.json",
            self.base_config.supported_formats,
        )
        self.telegram.set_chat_targets(self.users_by_chat_id)

    def _build_user_runtimes(self) -> List[UserRuntime]:
        profiles = self._load_user_profiles()
        runtimes: List[UserRuntime] = []

        for profile in profiles:
            config = Config(self.base_config_path)
            config.config_data = copy.deepcopy(config.config_data)
            config.config_data["audio"]["input_folder"] = profile.input_folder
            config.config_data["project"]["vault_path"] = profile.vault_path
            config.config_data["project"]["daily_notes_path"] = profile.daily_notes_path
            config.config_data["project"]["projects_path"] = profile.projects_path

            processor = TermuxProcessor(config)
            inbox = processor.config.audio_input_path
            queue_root = inbox.parent
            folders = QueueFolders(
                inbox=inbox,
                processing=queue_root / "_processing",
                archive=queue_root / "_archive",
                failed=queue_root / "_failed",
            )

            for folder in (folders.inbox, folders.processing, folders.archive, folders.failed):
                folder.mkdir(parents=True, exist_ok=True)

            runtimes.append(
                UserRuntime(
                    profile=profile,
                    processor=processor,
                    detector=StableFileDetector(self.stability_seconds),
                    folders=folders,
                )
            )

        return runtimes

    def _load_user_profiles(self) -> List[UserProfile]:
        users_file = self.base_config.config_dir / "telegram_users.json"
        if users_file.exists():
            payload = json.loads(users_file.read_text(encoding="utf-8"))
            profiles = []
            for entry in payload.get("users", []):
                profiles.append(
                    UserProfile(
                        chat_id=str(entry["chat_id"]),
                        name=entry["name"],
                        input_folder=entry["input_folder"],
                        vault_path=entry["vault_path"],
                        daily_notes_path=entry["daily_notes_path"],
                        projects_path=entry["projects_path"],
                    )
                )
            if profiles:
                return profiles

        fallback_chat_id = (self.base_config.config_dir / "telegram_allowed_chat_id.txt")
        if fallback_chat_id.exists():
            return [
                UserProfile(
                    chat_id=fallback_chat_id.read_text(encoding="utf-8").strip(),
                    name="default",
                    input_folder=self.base_config.config_data["audio"]["input_folder"],
                    vault_path=self.base_config.config_data["project"]["vault_path"],
                    daily_notes_path=self.base_config.config_data["project"]["daily_notes_path"],
                    projects_path=self.base_config.config_data["project"]["projects_path"],
                )
            ]

        return []

    def recover_processing_files(self) -> None:
        for runtime in self.users:
            leftovers = list(self._iter_audio_files(runtime, runtime.folders.processing))
            if not leftovers:
                continue

            LOGGER.warning(
                "Recovering %s file(s) left in processing queue for %s",
                len(leftovers),
                runtime.profile.name,
            )
            for path in leftovers:
                restored = self._unique_path(runtime.folders.inbox / path.name)
                path.replace(restored)
                LOGGER.warning("Moved %s back to inbox as %s", path.name, restored.name)

    def _iter_audio_files(self, runtime: UserRuntime, folder: Path) -> Iterable[Path]:
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in runtime.processor.config.supported_formats:
                continue
            yield path

    def _unique_path(self, target: Path) -> Path:
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = target.with_name(f"{stem}_{timestamp}{suffix}")
        counter = 1

        while candidate.exists():
            candidate = target.with_name(f"{stem}_{timestamp}_{counter}{suffix}")
            counter += 1

        return candidate

    def _claim_file(self, runtime: UserRuntime, source: Path) -> Optional[Path]:
        destination = self._unique_path(runtime.folders.processing / source.name)

        try:
            claimed = source.replace(destination)
            runtime.detector.forget(source)
            return claimed
        except FileNotFoundError:
            runtime.detector.forget(source)
            return None
        except OSError as error:
            LOGGER.warning("Could not claim %s yet: %s", source.name, error)
            return None

    def _archive_file(self, runtime: UserRuntime, source: Path) -> Path:
        target = self._unique_path(runtime.folders.archive / source.name)
        return source.replace(target)

    def _fail_file(self, runtime: UserRuntime, source: Path, reason: str) -> Path:
        target = self._unique_path(runtime.folders.failed / source.name)
        failed_path = source.replace(target)
        reason_path = failed_path.with_suffix(failed_path.suffix + ".error.txt")
        reason_path.write_text(reason + "\n", encoding="utf-8")
        return failed_path

    def process_once(self) -> bool:
        processed_any = False

        for runtime in self.users:
            for path in self._iter_audio_files(runtime, runtime.folders.inbox):
                if not runtime.detector.is_stable(path):
                    continue

                claimed = self._claim_file(runtime, path)
                if claimed is None:
                    continue

                processed_any = True
                self.telegram.send_message_to_chat(
                    runtime.profile.chat_id,
                    f"Started processing `{claimed.name}` for {runtime.profile.name}.",
                )
                result = runtime.processor.process_audio_file(claimed)

                if result.success:
                    archived = self._archive_file(runtime, claimed)
                    LOGGER.info(
                        "Archived processed audio as %s for %s",
                        archived.name,
                        runtime.profile.name,
                    )
                    self.telegram.send_message_to_chat(
                        runtime.profile.chat_id,
                        f"Finished processing `{archived.name}`.",
                    )
                    if result.note_path is not None:
                        self.telegram.send_document_to_chat(
                            runtime.profile.chat_id,
                            result.note_path,
                            caption=f"Daily note ready: {result.note_path.name}",
                        )
                else:
                    failed = self._fail_file(runtime, claimed, "Processing failed. See termux_daemon log.")
                    LOGGER.error("Moved failed audio to %s for %s", failed.name, runtime.profile.name)
                    self.telegram.send_message_to_chat(
                        runtime.profile.chat_id,
                        f"Processing failed for `{failed.name}`.\nError: {result.error[:800]}",
                    )

        return processed_any

    def _run_timeline_generation_for_user(self, runtime: UserRuntime) -> None:
        generated_files: List[Path] = []
        available_projects = runtime.processor.config.get_available_projects()
        if not available_projects:
            LOGGER.info("No projects available for timeline generation for %s", runtime.profile.name)
            return

        for project_name in available_projects:
            missing_weeks = runtime.processor.timeline_generator.get_missing_weeks(project_name)
            if not missing_weeks:
                continue

            project_generated = False
            LOGGER.info(
                "Generating %s missing weekly timeline file(s) for %s",
                len(missing_weeks),
                f"{runtime.profile.name}/{project_name}",
            )

            for year, week in missing_weeks:
                generated = runtime.processor.timeline_generator.create_weekly_summary_file(
                    project_name,
                    year,
                    week,
                )
                if generated is not None:
                    project_generated = True
                    generated_files.append(generated)

            if project_generated:
                runtime.processor.timeline_generator.update_timeline_index(project_name)

        if not generated_files:
            LOGGER.info("Timeline generation complete: no new files for %s", runtime.profile.name)
            return

        LOGGER.info(
            "Timeline generation complete: %s new file(s) for %s",
            len(generated_files),
            runtime.profile.name,
        )
        self.telegram.send_message_to_chat(
            runtime.profile.chat_id,
            f"Generated {len(generated_files)} weekly summary file(s).",
        )
        for summary_path in generated_files:
            self.telegram.send_document_to_chat(
                runtime.profile.chat_id,
                summary_path,
                caption=f"Weekly summary ready: {summary_path.name}",
            )

    def maybe_run_timeline(self) -> None:
        if self.timeline_day is None or self.timeline_hour is None:
            return

        now = datetime.now()
        if now.strftime("%a").lower() != self.timeline_day[:3]:
            return
        if now.hour != self.timeline_hour:
            return

        run_key = now.strftime("%Y-%m-%d-%H")
        if self.last_timeline_run == run_key:
            return

        LOGGER.info("Running scheduled timeline generation")
        for runtime in self.users:
            self._run_timeline_generation_for_user(runtime)
        self.last_timeline_run = run_key

    def run_forever(self) -> None:
        self.recover_processing_files()
        for runtime in self.users:
            LOGGER.info(
                "User %s mapped to chat %s | inbox=%s | vault=%s",
                runtime.profile.name,
                runtime.profile.chat_id,
                runtime.folders.inbox,
                runtime.processor.config.vault_path,
            )

        while self.running:
            try:
                for download in self.telegram.poll_and_download():
                    runtime = self.users_by_chat_id.get(download.chat_id)
                    if runtime is not None:
                        runtime.detector.mark_stable(download.path)
                self.process_once()
                self.maybe_run_timeline()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                self.running = False
            except Exception as error:  # pragma: no cover - runtime defensive logging
                LOGGER.exception("Daemon loop error: %s", error)
                time.sleep(self.poll_interval)

        LOGGER.info("Daemon stopped")

    def stop(self, *_args) -> None:
        LOGGER.info("Shutdown requested")
        self.running = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unattended Termux daemon for daily notes")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Config file name stored inside the config directory",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Seconds between inbox scans",
    )
    parser.add_argument(
        "--stability-seconds",
        type=int,
        default=45,
        help="How long a file must stay unchanged before processing",
    )
    parser.add_argument(
        "--timeline-day",
        type=str,
        default="sat",
        help="Three-letter weekday for automatic timeline generation; use 'off' to disable",
    )
    parser.add_argument(
        "--timeline-hour",
        type=int,
        default=22,
        help="Hour (0-23) to run timeline generation on the selected day",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single inbox scan and exit",
    )
    return parser


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "termux_daemon.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    timeline_day = None if args.timeline_day.lower() == "off" else args.timeline_day
    if timeline_day is not None and args.timeline_hour not in range(24):
        parser.error("--timeline-hour must be between 0 and 23")

    configure_logging(Path("logs"))

    try:
        daemon = TermuxDaemon(
            args.config,
            poll_interval=args.poll_interval,
            stability_seconds=args.stability_seconds,
            timeline_day=timeline_day,
            timeline_hour=args.timeline_hour if timeline_day else None,
        )

        signal.signal(signal.SIGINT, daemon.stop)
        signal.signal(signal.SIGTERM, daemon.stop)

        if args.once:
            daemon.recover_processing_files()
            daemon.process_once()
            daemon.maybe_run_timeline()
            return 0

        daemon.run_forever()
        return 0
    except Exception as error:
        LOGGER.exception("Startup failed: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
