# Daily Notes

Daily Notes turns voice notes into structured Obsidian notes, project todo lists, and weekly summaries.

The current recommended deployment is a small Linux server running a Telegram-driven daemon:

- users send audio to a Telegram bot
- the daemon downloads and processes the files
- notes are written into one or more local vault folders
- `rclone` keeps selected vault folders synced with OneDrive

This repository also still supports the original interactive CLI flow in `main.py`, and the same cloud-based daemon can run on Android through Termux.

## What It Does

- Transcribes audio with AssemblyAI or local Whisper
- Generates structured daily notes with OpenAI or DeepSeek
- Extracts project todos into per-project `todo.md` files
- Builds weekly summaries for each project
- Supports multiple users with isolated inboxes and vaults
- Sends progress updates and generated files back to Telegram

## Recommended Architecture

For a simple Linux machine:

1. Create one local vault root per user.
2. Configure a Telegram bot and map each chat ID to a user.
3. Run `server_daemon.py` continuously.
4. Configure `rclone` remotes for each user's OneDrive.
5. Let the daemon do immediate `rclone copy` pushes and periodic `rclone bisync`.

The daemon itself is sync-method agnostic. It only reads and writes local folders.

## Requirements

- Python 3.10+
- `ffmpeg` if you want local Whisper workflows
- `rclone` if you want automatic OneDrive sync
- AssemblyAI API key for cloud transcription
- OpenAI or DeepSeek API key for note generation
- Telegram bot token for bot-driven ingestion

Minimal Python packages for the cloud daemon are:

```bash
pip install openai assemblyai PyYAML mutagen
```

## Project Entry Points

- `server_daemon.py`
  - generic Linux-first daemon entrypoint
  - recommended for unattended Telegram-driven processing
- `termux_daemon.py`
  - compatibility wrapper around `server_daemon.py`
  - useful if you already launch the old name on Termux
- `main.py`
  - interactive/manual CLI for desktop workflows
- `server.py`
  - older filesystem watcher flow

## Linux Setup

### 1. Clone and create the environment

```bash
git clone <your-repo-url> daily_notes
cd daily_notes
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install openai assemblyai PyYAML mutagen
```

If you want the full original desktop stack instead:

```bash
pip install -r requirments.txt
```

### 2. Configure shared processing settings

Create or edit `config/config.yaml` with Linux paths. Example:

```yaml
audio:
  delete_after_processing: false
  input_folder: inbox/default
  max_duration_seconds: 1800
  min_duration_seconds: 5
  supported_formats:
    - .mp3
    - .wav
    - .m4a
    - .aac
    - .ogg
    - .flac

output:
  date_format: "%Y-%m-%d"
  include_audio_filename: true
  include_processing_timestamp: true
  save_transcript: true
  transcript_folder: "transcripts"

processing:
  llm_provider: openai
  model: gpt-4.1-mini
  weekly_summary_model: gpt-4.1
  max_tokens: 4000
  temperature: 0.4
  audio_model: assembly
  assembly_model: slam
  language_code: "en"

project:
  vault_path: data/default/Vault
  daily_notes_path: data/default/Vault/0. Daily Notes
  projects_path: data/default/Vault/1. Projects

debug:
  save_llm_conversations: false
  debug_folder: "debug_logs"
```

### 3. Add API keys

Create:

- `config/assembly_api_key.txt`
- `config/openai_api_key.txt` or `config/deepseek_api_key.txt`
- `config/telegram_bot_token.txt`

Examples:

```bash
printf '%s\n' "YOUR_ASSEMBLYAI_KEY" > config/assembly_api_key.txt
printf '%s\n' "YOUR_OPENAI_KEY" > config/openai_api_key.txt
printf '%s\n' "YOUR_TELEGRAM_BOT_TOKEN" > config/telegram_bot_token.txt
```

### 4. Configure users

`config/telegram_users.json` maps each Telegram chat to one local vault and one optional sync policy.

Example:

```json
{
  "users": [
    {
      "chat_id": "111111111",
      "name": "alice",
      "input_folder": "inbox/alice",
      "vault_path": "data/alice/Vault",
      "daily_notes_path": "data/alice/Vault/0. Daily Notes",
      "projects_path": "data/alice/Vault/1. Projects",
      "sync": {
        "enabled": true,
        "remote": "onedrive_alice",
        "remote_path": "Obsidian/AliceVault",
        "local_subpaths": ["0. Daily Notes", "1. Projects"],
        "interval_minutes": 10,
        "immediate_push_on_change": true,
        "notify_on_error": true
      }
    },
    {
      "chat_id": "222222222",
      "name": "bob",
      "input_folder": "inbox/bob",
      "vault_path": "data/bob/Vault",
      "daily_notes_path": "data/bob/Vault/0. Daily Notes",
      "projects_path": "data/bob/Vault/1. Projects",
      "sync": {
        "enabled": true,
        "remote": "onedrive_bob",
        "remote_path": "Obsidian/BobVault",
        "local_subpaths": ["0. Daily Notes", "1. Projects"],
        "interval_minutes": 10,
        "immediate_push_on_change": true,
        "notify_on_error": true
      }
    }
  ]
}
```

What the daemon expects per user:

- an inbox folder for incoming Telegram audio
- a vault root
- `0. Daily Notes` under that vault
- `1. Projects` under that vault

It creates `_processing`, `_archive`, and `_failed` automatically next to the inbox.

### 5. Configure Telegram

Use `@BotFather` to create a bot, then send at least one message to it from each user chat.

If you do not know the chat IDs yet:

1. start the daemon with only `telegram_bot_token.txt` configured
2. message the bot from the target chats
3. inspect `logs/server_daemon.log`
4. copy the logged chat IDs into `config/telegram_users.json`

### 6. Configure rclone

Set up one remote per user, for example:

- `onedrive_alice`
- `onedrive_bob`

The daemon can then:

- run `rclone copy` immediately after creating notes
- run periodic `rclone bisync` for the configured subfolders

If you bootstrap a new user from OneDrive, do the first `bisync --resync` manually before enabling periodic sync in the daemon.

## Running the Daemon

One-shot test:

```bash
source .venv/bin/activate
python server_daemon.py --once
```

Continuous run:

```bash
source .venv/bin/activate
python server_daemon.py
```

Typical Linux production pattern:

```bash
tmux new -s daily-notes
source .venv/bin/activate
python server_daemon.py
```

Detach with `Ctrl-b` then `d`, reattach with:

```bash
tmux attach -t daily-notes
```

## Daily Workflow

- send an audio file or voice message to the Telegram bot
- the daemon downloads it and waits until it is stable
- transcription and note generation run automatically
- the daily note, todos, and weekly summaries are written into the local vault
- the daemon pushes or syncs the configured folders with `rclone`
- the generated note is also sent back to the user in Telegram

## Troubleshooting

- If the bot does not react, check `config/telegram_bot_token.txt` and `config/telegram_users.json`.
- If files stay in the inbox, increase `--stability-seconds`.
- If sync fails, inspect `logs/server_daemon.log` and verify the user's `sync.remote`.
- If `rclone bisync` complains about missing prior listings, run the first `--resync` manually for that folder pair.
- If project classification is poor, create real project directories inside `1. Projects` so the model has candidates to match.

## Termux Note

This same cloud-first daemon also runs on an old Android phone through Termux. That is the setup currently used in practice here: Telegram for ingestion, AssemblyAI/OpenAI or DeepSeek for cloud processing, and `rclone` for OneDrive sync. In principle, the same codebase can also run on a Linux machine with a GPU and switch back to local Whisper for fully local processing.

