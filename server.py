"""
Daily Notes Server
Monitors audio inbox for new files and runs scheduled tasks
"""
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import sys
import time
from pathlib import Path
from datetime import datetime
import schedule
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.daily_notes_processor import DailyNotesProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("daily_notes_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DailyNotesServer")

class AudioFileHandler(FileSystemEventHandler):
    def __init__(self, processor):
        self.processor = processor
        self.processing_files = set()
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        
        # Check if it's an audio file
        if file_path.suffix.lower() in self.processor.config.supported_formats:
            # Avoid duplicate processing
            if str(file_path) in self.processing_files:
                return
                
            logger.info(f"New audio file detected: {file_path.name}")
            
            # Wait a moment to ensure file is completely written
            time.sleep(2)
            
            # Add to processing set
            self.processing_files.add(str(file_path))
            
            try:
                # Process the file
                success = self.processor.process_audio_file(file_path)
                if success:
                    logger.info(f"Successfully processed: {file_path.name}")
                else:
                    logger.error(f"Failed to process: {file_path.name}")
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
            finally:
                # Remove from processing set
                self.processing_files.discard(str(file_path))

def run_weekly_workflow(processor):
    """Run the weekly timeline generation"""
    logger.info("Running weekly workflow...")
    try:
        results = processor.timeline_generator.process_all_projects()
        total = sum(results.values())
        if total > 0:
            logger.info(f"Generated {total} timeline entries across {len(results)} projects")
            for project, count in results.items():
                if count > 0:
                    logger.info(f"  - {project}: {count} entries")
        else:
            logger.info("No missing weekly summaries found")
    except Exception as e:
        logger.error(f"Error running weekly workflow: {e}")

def main():
    logger.info("Starting Daily Notes Server")
    
    # Initialize the processor
    processor = DailyNotesProcessor()
    
    # Setup file system observer
    event_handler = AudioFileHandler(processor)
    observer = Observer()
    observer.schedule(event_handler, str(processor.config.audio_input_path), recursive=False)
    observer.start()
    
    # Schedule weekly workflow
    schedule.every().saturday.at("22:00").do(run_weekly_workflow, processor)
    
    logger.info(f"Watching for audio files in: {processor.config.audio_input_path}")
    logger.info("Weekly workflow scheduled for Saturdays at 22:00")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
        observer.stop()
    
    observer.join()
    logger.info("Server stopped")

if __name__ == "__main__":
    main()