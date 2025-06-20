"""
Audio-to-Obsidian Daily Notes Generator
Phase 1: Core audio processing and note generation

Usage:
    python main.py                    # Interactive mode
    python main.py --batch            # Process all files once
    python main.py --file audio.mp3   # Process single file
    python main.py --todos audio.mp3  # Extract todos only from file
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import argparse
import sys
from pathlib import Path
from src.daily_notes_processor import DailyNotesProcessor

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def main():
    parser = argparse.ArgumentParser(description='Audio to Obsidian Daily Notes')
    parser.add_argument('--batch', action='store_true', help='Process all audio files and exit')
    parser.add_argument('--file', type=str, help='Process specific audio file as daily note')
    parser.add_argument('--todos', type=str, help='Process specific file for todos only')
    parser.add_argument('--timeline', action='store_true', help='Generate missing weekly summaries and exit')
    parser.add_argument('--config', type=str, default='config.yaml', help='Config file name (in config directory)')
    
    args = parser.parse_args()
    
    try:
        processor = DailyNotesProcessor(args.config)
        
        if args.file:
            # Process single file as daily note
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"Error: File not found: {file_path}")
                sys.exit(1)
            
            # Move file to inbox if not already there
            if file_path.parent != processor.config.audio_input_path:
                inbox_path = processor.config.audio_input_path / file_path.name
                file_path.rename(inbox_path)
                file_path = inbox_path
                print(f"Moved {args.file} to inbox")
            
            success = processor.process_audio_file(file_path)
            sys.exit(0 if success else 1)
            
        elif args.todos:
            # Process single file for todos only
            file_path = Path(args.todos)
            if not file_path.exists():
                print(f"Error: File not found: {file_path}")
                sys.exit(1)
            
            # Move file to inbox if not already there
            if file_path.parent != processor.config.audio_input_path:
                inbox_path = processor.config.audio_input_path / file_path.name
                file_path.rename(inbox_path)
                file_path = inbox_path
                print(f"Moved {args.todos} to inbox")
            
            success = processor.process_audio_for_todos(file_path)
            sys.exit(0 if success else 1)
            
        elif args.batch:
            # Process all files and exit
            results = processor.process_all_audio()
            sys.exit(0 if results['failed'] == 0 else 1)

        elif args.timeline:
            # Generate missing weekly summaries and exit
            print("🔄 Generating missing weekly summaries...")
            results = processor.timeline_generator.process_all_projects()

            total = sum(results.values())
            if total > 0:
                print(f"✅ Generated {total} timeline entries across {len(results)} projects")
                for project, count in results.items():
                    if count > 0:
                        print(f"  - {project}: {count} entries")
            else:
                print("ℹ️ No missing weekly summaries found")

            sys.exit(0)

        else:
            # Interactive mode
            processor.run_interactive()
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()