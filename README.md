# 🎙️ Voice-to-Notes: Audio Transcription for Obsidian

Voice-to-Notes is a Python application that converts audio recordings into structured, organized notes in your Obsidian vault. Record your thoughts on the go, and the app will transcribe them, categorize them by project, extract action items, and even generate weekly summaries.

![Voice to Notes Banner](https://via.placeholder.com/800x200?text=Voice+to+Notes)

## 🌟 Features

- **Audio Transcription** - Convert voice recordings to text using either:
  - 🤗 Locally-run Whisper AI (full privacy, works offline)
  - ☁️ AssemblyAI API (better accuracy for specialized terminology)
  
- **Structured Notes** - Automatically formats transcripts into organized sections:
  - 📋 Summary
  - ✅ Completed Tasks
  - 🚧 In Progress/Blockers
  - 📝 Next Steps
  - 💭 Thoughts & Ideas
  
- **Project Organization** - Automatically detects which project you're talking about
  
- **Todo Extraction** - Identifies and extracts action items from your recordings:
  - Prioritizes tasks (🔴 High, 🟠 Medium, 🟢 Low)
  - Links back to the source note
  - Maintains a consolidated todo list for each project
  - Extract todos without creating full daily notes
  
- **Smart Date Detection** - Automatically extracts dates from audio filenames (e.g., Daily_Log_dd-mm-yyyy)
  
- **Timeline Generation** - Creates weekly summaries from your daily notes
  
- **Cross-Platform** - Works on:
  - 💻 Windows/Mac/Linux (full features)
  - 📱 Android (through Pydroid 3)
  
- **Voice Recording** - Record directly through the app (desktop only)

## 📋 Requirements

- Python 3.8+
- FFmpeg (for audio processing)
- PyAudio (for recording, desktop only)
- Obsidian (for viewing the generated notes)

### Optional:
- GPU acceleration (for faster Whisper transcription)
- AssemblyAI API key (if using cloud transcription)

## 🚀 Installation

### Desktop Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/voice-to-notes.git
   cd voice-to-notes
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv .venv
   # On Windows
   .venv\Scripts\activate
   # On macOS/Linux
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install FFmpeg:
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt install ffmpeg`

5. Configure the application:
   ```bash
   # Create API key files (if using AssemblyAI)
   echo "your_api_key_here" > daily_notes/config/assembly_api_key.txt
   echo "your_api_key_here" > daily_notes/config/openai_api_key.txt
   ```

6. Edit `daily_notes/config/config.yaml` to set your Obsidian vault path and other preferences.

### Android Installation

1. Install Pydroid 3 from the Google Play Store
2. Download the repository as a ZIP file and extract it on your Android device
3. Open `android_main.py` or `android_web.py` in Pydroid 3
4. Install required packages through Pydroid's PIP menu
5. Configure API keys and paths in the config file
6. Use Folder Sync or similar apps to sync your Obsidian vault. 

## 🔧 Configuration

The application can be configured by editing `daily_notes/config/config.yaml`:

```yaml
project:
  vault_path: path/to/your/obsidian/vault
  daily_notes_path: path/to/daily/notes/folder
  projects_path: path/to/projects/folder

audio:
  input_folder: AudioInbox
  supported_formats: [.mp3, .wav, .m4a, .aac, .ogg, .flac]
  max_duration_seconds: 1800  # 30 minutes
  min_duration_seconds: 5
  delete_after_processing: true

processing:
  whisper_model: large-v3  # Options: tiny, base, small, medium, large-v1, large-v2, large-v3
  gpt_model: gpt-4.1-mini  # Model for daily note generation
  weekly_summary_model: gpt-4.1  # Model for weekly summaries
  audio_model: whisper  # Options: whisper, assembly
  # ... additional processing options
```

## 📱 Usage

### Desktop (Interactive Mode)

Run the application in interactive mode:

```bash
python daily_notes/main.py
```

This provides a menu with options to:
1. 📁 Scan for new audio files
2. 🎤 Record a new voice note
   - Record directly through the application
   - Configure audio devices
3. 📅 Generate timeline entries
4. 📋 Show current settings
5. ✅ Extract todos from audio (NEW!)
6. 🚪 Exit

### Desktop (Command Line)

```bash
# Process all audio files in the inbox
python daily_notes/main.py --batch

# Process a specific audio file
python daily_notes/main.py --file path/to/audio.mp3

# Extract todos from audio without creating a daily note (NEW!)
python daily_notes/main.py --todos path/to/audio.mp3

# Generate missing weekly summaries
python daily_notes/main.py --timeline
```

### Android

Run the Android version with these features:
- Process audio files as full daily notes
- Extract todos only from audio files (NEW!)
- Generate timeline entries
- View current settings

## 🔄 Workflow

1. **Record your thoughts** - Use the app's recording feature or any audio recorder
   - **TIP**: Name files like "Daily_Log_dd-mm-yyyy.mp3" for automatic date detection
2. **Process the audio** - Choose between:
   - Full daily note processing
   - Todo extraction only (NEW!)
3. **Review the note** - The app generates a structured note in your Obsidian vault
4. **Check extracted todos** - Action items are added to project-specific todo lists
5. **Generate weekly summaries** - Create timeline entries that summarize your week

## 📂 Project Structure

```
daily_notes/
├── config/                  # Configuration files
│   ├── config.yaml          # Main configuration
│   ├── openai_api_key.txt   # OpenAI API key
│   └── assembly_api_key.txt # AssemblyAI API key
├── src/                     # Source code
│   ├── audio_processor.py   # Audio transcription (Whisper)
│   ├── android_audio_processor.py # Android-specific transcription
│   ├── audio_recorder.py    # Audio recording capabilities
│   ├── config.py            # Configuration handling
│   ├── daily_notes_processor.py # Main processing logic
│   ├── note_generator.py    # Note generation
│   ├── timeline_generator.py # Weekly summary generation
│   ├── todo_manager.py      # Todo extraction and management
│   └── todo_extractor.py    # NEW: Standalone todo extraction
├── AudioInbox/              # Folder for audio files to process
├── main.py                  # Main entry point
├── android_main.py          # Android console interface
└── android_web.py           # Android web interface
```

## 📝 Notes Format

### Daily Notes
Generated daily notes follow this structure:

```markdown
---
date: 2023-07-10
project: ProjectName
tags: [daily, work-log, project/ProjectName, transcript]
---

# Daily Log: 2023-07-10

## 📋 Summary
Concise summary of the day's work...

## ✅ Completed Today
- Task 1 completed
- Task 2 completed

## 🚧 In Progress / Blockers
- Current blockers and works in progress

## 📝 Next Steps
- Upcoming tasks and priorities

## 💭 Thoughts & Ideas
- Insights and creative ideas

## 📝 Full Transcript
[View complete transcript](transcripts/2023-07-10_ProjectName_transcript.md)

---
*Generated from audio transcript on 2023-07-10 14:32:45*
```

### Todo Lists
Todo items are collected in project-specific todo lists:

```markdown
---
tags: [todo, project/ProjectName]
---

# ProjectName Todo List

- [ ] 🔴 High priority task _context_ *[[2023-07-10_ProjectName|Source]]*
- [ ] 🟠 Medium priority task *[[2023-07-09_ProjectName|Source]]*
- [ ] 🟢 Low priority task *[[2023-07-08_ProjectName|Source]]*
```

### Todo-Only Transcripts (NEW!)
When processing audio for todos only:

```markdown
---
date: 2023-07-10
project: ProjectName
tags: [transcript, todo-extract, project/ProjectName]
---

# Todo Extract: 2023-07-10 - ProjectName

[Full transcript text...]
```

### Weekly Summaries
Weekly summaries provide an overview of the week's work:

```markdown
---
tags: [timeline, weekly-summary, project/ProjectName]
week: 2023-W28
date_range: 2023-07-10 to 2023-07-16
---

# Week 2023-W28: 2023-07-10 to 2023-07-16 - ProjectName

## 📊 Week Summary
Overview of the week's accomplishments...

## 🎯 Key Accomplishments
- Major milestones reached
- Features completed

## 💭 Insights & Thoughts
- Important realizations and ideas

## 🚧 Progress Indicators
- Current status and blockers

## 📝 Next Week Focus
- Priorities for the coming week

## 📄 Daily Notes References
- [2023-07-10: Daily Log](2023-07-10_ProjectName.md)
- [2023-07-11: Daily Log](2023-07-11_ProjectName.md)
```

## 📣 Tips for Effective Voice Notes

1. **Start with project context** - Begin by mentioning which project you're working on
2. **Use clear sections** - Explicitly mention "things I completed today", "current blockers", etc.
3. **Flag todo items** - Use phrases like "todo", "need to", "tomorrow I should" to flag action items
4. **Indicate priority** - Mention "high priority", "urgent", or "low priority" for tasks
5. **Name your files with dates** - **NEW**: Use format "Daily_Log_dd-mm-yyyy.mp3" for automatic date detection
6. **Record quick todos** - **NEW**: Use the todo-only extraction for quick task capture without full daily notes
7. **Speak clearly** - Pause between thoughts for better transcription accuracy

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🙏 Acknowledgements

- [OpenAI Whisper](https://github.com/openai/whisper) for the speech recognition models
- [AssemblyAI](https://www.assemblyai.com/) for cloud transcription capabilities
- [Obsidian](https://obsidian.md/) for the note-taking system

---

*Made with ❤️ for Obsidian users who prefer talking to typing*