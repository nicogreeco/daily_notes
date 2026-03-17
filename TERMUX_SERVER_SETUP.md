# Termux Phone Server Setup

This setup keeps the system simple:

- a Telegram bot moves audio files from your main phone to the old phone.
- `termux_daemon.py` processes those files on the old phone.
- `FolderSync` syncs the generated Obsidian vault back to OneDrive.
- one bot can now serve multiple people, each with their own local inbox and vault paths.

That means:

- audio transport does not depend on OneDrive timing
- notes still end up in OneDrive for Obsidian on all devices
- the old phone can run unattended without a UI

## Recommended Flow

1. Record audio on your main phone.
2. Share the recording to your Telegram bot chat.
3. The daemon downloads the file into the local inbox on the old phone.
4. `termux_daemon.py` waits until the file is stable, then processes it.
5. The daemon routes the file to the correct user based on Telegram chat id.
6. The daemon writes notes and todos into that user's local vault.
7. FolderSync syncs each vault folder to the matching OneDrive account or folder pair.
8. Obsidian on each person's devices receives the updated notes through OneDrive.

## Project Scripts Refresher

- `main.py`
  - desktop-style CLI entrypoint
  - good for manual runs or one-shot batch commands
- `server.py`
  - desktop watcher using `watchdog`
  - better suited to regular computers than Android sync folders
- `termux_daemon.py`
  - unattended Android/Termux daemon
  - polls a Telegram bot for audio
  - downloads files into the inbox
  - sends status updates plus final daily/weekly note files back to Telegram
  - best fit for your old phone server

## Folder Layout on the Old Phone

Use Android shared storage so Termux, Syncthing, and FolderSync can all see the same folders.

Recommended local folders:

- `~/storage/shared/DailyNotes/AudioInbox`
- `~/storage/shared/DailyNotes/Vault`
- `~/storage/shared/DailyNotes/Vault/0. Daily Notes`
- `~/storage/shared/DailyNotes/Vault/1. Projects`

The daemon also creates these queue folders next to the inbox:

- `~/storage/shared/DailyNotes/_processing`
- `~/storage/shared/DailyNotes/_archive`
- `~/storage/shared/DailyNotes/_failed`

## 1. Install Termux

Install:

- Termux
- Termux:Boot (optional, recommended for auto-start)

Inside Termux:

```bash
pkg update && pkg upgrade
pkg install python git tmux
termux-setup-storage
```

If you plan to also experiment with local Whisper later:

```bash
pkg install ffmpeg
```

## 2. Clone the Project

```bash
cd ~
git clone <your-repo-url> daily_notes
cd daily_notes
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirments.txt
```

## 3. Create the Shared Folders

```bash
mkdir -p ~/storage/shared/DailyNotes/AudioInbox
mkdir -p ~/storage/shared/DailyNotes/Vault/"0. Daily Notes"
mkdir -p ~/storage/shared/DailyNotes/Vault/"1. Projects"
```

## 4. Configure the App

Edit `config/config.yaml` so the old phone uses AssemblyAI and your shared storage paths.

Example:

```yaml
audio:
  delete_after_processing: false
  input_folder: ../storage/shared/DailyNotes/AudioInbox
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
  transcript_folder: transcripts

processing:
  llm_provider: openai
  model: gpt-4.1-mini
  weekly_summary_model: gpt-4.1
  max_tokens: 4000
  temperature: 0.4
  audio_model: assembly
  assembly_model: slam
  language_code: en

project:
  vault_path: ../storage/shared/DailyNotes/Vault
  daily_notes_path: ../storage/shared/DailyNotes/Vault/0. Daily Notes
  projects_path: ../storage/shared/DailyNotes/Vault/1. Projects

debug:
  save_llm_conversations: false
  debug_folder: debug_logs
```

Why these paths work:

- the repo lives at `~/daily_notes`
- `Config` resolves paths relative to the repo root
- `../storage/shared/...` points to Termux shared storage

## 5. Add API Keys

Create the files:

- `config/assembly_api_key.txt`
- `config/openai_api_key.txt` or `config/deepseek_api_key.txt`
- `config/telegram_bot_token.txt`
- `config/telegram_users.json` for multi-user setups

Examples:

```bash
echo "YOUR_ASSEMBLYAI_KEY" > config/assembly_api_key.txt
echo "YOUR_OPENAI_KEY" > config/openai_api_key.txt
```

Or for DeepSeek:

```bash
echo "YOUR_DEEPSEEK_KEY" > config/deepseek_api_key.txt
```

For Telegram, also create:

```bash
echo "YOUR_TELEGRAM_BOT_TOKEN" > config/telegram_bot_token.txt
```

For one user only, you can still use:

```bash
echo "YOUR_TELEGRAM_CHAT_ID" > config/telegram_allowed_chat_id.txt
```

For multiple users, create `config/telegram_users.json` instead.

Notes:

- the daemon maps each configured chat id to one user profile
- it can receive `voice`, `audio`, and Telegram documents with supported audio extensions
- it sends progress updates and generated notes back into each sender's own chat

## 6. Create the Telegram Bot

Use BotFather in Telegram:

1. Open Telegram
2. Start a chat with `@BotFather`
3. Run `/newbot`
4. Pick a bot name and username
5. Copy the token into `config/telegram_bot_token.txt`

Then send at least one message to your bot from each chat you want to use.

To discover your chat id, the easiest approach is:

1. temporarily start the daemon without `telegram_allowed_chat_id.txt` and without `telegram_users.json`
2. send a message to the bot
3. check `logs/termux_daemon.log` for the logged `chat_id`
4. save the resulting ids into `config/telegram_users.json`

If you already know the chat ids, you can skip discovery mode and write the file directly.

## 6b. Configure Multiple Users

Create `config/telegram_users.json` like this:

```json
{
  "users": [
    {
      "chat_id": "111111111",
      "name": "alice",
      "input_folder": "../storage/shared/DailyNotes/alice/AudioInbox",
      "vault_path": "../storage/shared/DailyNotes/alice/Vault",
      "daily_notes_path": "../storage/shared/DailyNotes/alice/Vault/0. Daily Notes",
      "projects_path": "../storage/shared/DailyNotes/alice/Vault/1. Projects"
    },
    {
      "chat_id": "222222222",
      "name": "bob",
      "input_folder": "../storage/shared/DailyNotes/bob/AudioInbox",
      "vault_path": "../storage/shared/DailyNotes/bob/Vault",
      "daily_notes_path": "../storage/shared/DailyNotes/bob/Vault/0. Daily Notes",
      "projects_path": "../storage/shared/DailyNotes/bob/Vault/1. Projects"
    }
  ]
}
```

How it works:

- each Telegram chat id becomes one user
- each user gets a separate inbox
- each user gets a separate vault tree
- each user can have their own FolderSync pair to OneDrive

If `telegram_users.json` exists, the daemon uses it.

If it does not exist, the daemon falls back to the older single-user mode with:

- `config/telegram_allowed_chat_id.txt`
- the default paths from `config/config.yaml`

## 7. Set Up FolderSync for the Vault

Keep using OneDrive only for the vault.

Create one FolderSync pair per person:

- local: that person's local vault folder
- remote: that person's OneDrive vault folder

Recommended mode:

- two-way sync if you edit the vault on multiple devices

Be aware:

- two-way sync can still create conflicts if the same note is edited at the same time on different devices
- that is normal for markdown vault sync in general, not specific to this daemon

## 8. Test Once Manually

Activate the environment:

```bash
cd ~/daily_notes
source .venv/bin/activate
python termux_daemon.py --once
```

If there is already an audio file in the inbox, the daemon should:

- process it
- write notes into the vault
- move the audio into `_archive`

If Telegram is configured, it will also:

- accept new audio messages from each configured user's chat
- send processing progress updates
- send the generated daily note back to the matching chat
- send weekly summary files to the matching chat when they are created

If something fails, the audio goes to `_failed` and a sidecar `.error.txt` file is created.

Logs are written to:

- `logs/termux_daemon.log`

## 9. Run the Daemon Continuously

The simplest reliable method is `tmux`.

Start a session:

```bash
cd ~/daily_notes
tmux new -s daily-notes
source .venv/bin/activate
python termux_daemon.py
```

Detach:

- press `Ctrl-b`, then `d`

Reattach later:

```bash
tmux attach -t daily-notes
```

Default behavior:

- scan every 30 seconds
- require a file to stay unchanged for 45 seconds
- run timeline generation on Saturday at 22:00
- poll Telegram during each loop

You can customize that:

```bash
python termux_daemon.py --poll-interval 20 --stability-seconds 60 --timeline-day sat --timeline-hour 21
```

Disable automatic timelines:

```bash
python termux_daemon.py --timeline-day off
```

## 10. Optional Auto-Start on Reboot

If you install Termux:Boot, create:

- `~/.termux/boot/start_daily_notes.sh`

Example:

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/daily_notes || exit 1
source .venv/bin/activate
tmux new-session -d -s daily-notes "python termux_daemon.py"
```

Make it executable:

```bash
chmod +x ~/.termux/boot/start_daily_notes.sh
```

## 11. Android Reliability Settings

On the old phone:

- disable battery optimization for Termux
- allow background activity for Termux
- keep the phone on charger if possible
- keep Wi-Fi enabled

These settings matter more than code changes for long-running reliability.

## How the Daemon Handles Files

The daemon keeps things simple:

- Telegram downloads audio into `AudioInbox`
- for multi-user mode, each user has their own `AudioInbox`
- it waits until they are stable
- it renames one into `_processing`
- if processing succeeds, it moves it into `_archive`
- if processing fails, it moves it into `_failed`

That avoids repeatedly processing the same file and makes recovery easy.

If the phone or Termux dies mid-run:

- leftover files in `_processing` are moved back into `AudioInbox` on next startup

## Suggested Daily Use

- record on your main phone
- share the recording to your Telegram bot chat
- let the old phone process automatically
- read progress updates and receive the final note back in Telegram
- open Obsidian on that person's devices after FolderSync completes

## Troubleshooting

- No notes are created
  - check `logs/termux_daemon.log`
  - check API key files
  - confirm `audio_model: assembly`
- Bot does not react
  - confirm `telegram_bot_token.txt` exists
  - confirm the sender's chat id exists in `telegram_users.json`, or in `telegram_allowed_chat_id.txt` for single-user mode
  - make sure you started the bot chat at least once in Telegram
- Files stay in `AudioInbox`
  - the file may still be downloading
  - wait longer or raise `--stability-seconds`
- Files move to `_failed`
  - open the `.error.txt` sidecar file
  - inspect `logs/termux_daemon.log`
- Vault does not appear on other devices
  - check FolderSync status
  - confirm the local vault path matches `config/config.yaml`

## Minimal Command Summary

Install and test:

```bash
cd ~/daily_notes
source .venv/bin/activate
python termux_daemon.py --once
```

Run continuously:

```bash
cd ~/daily_notes
source .venv/bin/activate
python termux_daemon.py
```
