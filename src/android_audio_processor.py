import os
import tempfile
from pathlib import Path
import assemblyai as aai
from mutagen import File as MutagenFile
import wave

class AndroidAudioProcessor:
    def __init__(self, config):
        self.config = config
        
        # Configure AssemblyAI
        if self.config.assembly_api_key:
            aai.settings.api_key = self.config.assembly_api_key
            print("✓ AssemblyAI API key configured")
        else:
            print("⚠️ AssemblyAI API key not found. Transcription will fail.")
    
    def validate_audio(self, audio_path, max_duration=None, min_duration=None):
        """Validate audio file format and duration without ffprobe"""
        if max_duration is None:
            max_duration = self.config.max_duration
        if min_duration is None:
            min_duration = self.config.min_duration

        audio_path = Path(audio_path)

        # Check if file exists
        if not audio_path.exists():
            return False, f"File not found: {audio_path}"

        # Check file extension
        suffix = audio_path.suffix.lower()
        if suffix not in self.config.supported_formats:
            return False, f"Unsupported format: {suffix}"

        # Try Mutagen first (supports mp3, flac, m4a, ogg, etc.)
        try:
            audio = MutagenFile(str(audio_path))
            if audio is None or not hasattr(audio.info, "length"):
                raise ValueError("Mutagen could not read duration")
            duration = audio.info.length
        except Exception:
            # Fallback for WAV using wave module
            if suffix == ".wav":
                try:
                    with wave.open(str(audio_path), 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration = frames / float(rate)
                except wave.Error as e:
                    return False, f"Cannot read WAV file: {e}"
            else:
                return False, "Unable to determine duration (unsupported format for Android)"

        # Check duration limits
        if duration < min_duration:
            return False, f"Audio too short: {duration:.1f}s (minimum: {min_duration}s)"
        if duration > max_duration:
            return False, f"Audio too long: {duration:.1f}s (maximum: {max_duration}s)"

        return True, f"Valid audio file: {duration:.1f}s"
    
    def transcribe(self, audio_path):
        """Transcribe audio file using AssemblyAI"""
        print(f"Transcribing: {Path(audio_path).name}")
        
        # Validate audio first
        is_valid, message = self.validate_audio(audio_path)
        if not is_valid:
            raise Exception(f"Audio validation failed: {message}")
        
        print(f"✓ Audio validation passed: {message}")
        
        # Transcribe with AssemblyAI
        return self._transcribe_with_assembly(audio_path)
    
    def _transcribe_with_assembly(self, audio_path):
        """Transcribe using AssemblyAI"""
        print(f"Transcribing with AssemblyAI ({self.config.assembly_model})...")
        
        try:
            # Configure AssemblyAI
            if self.config.assembly_model == 'nano':
                config = aai.TranscriptionConfig(
                    language_code=self.config.language_code, 
                    speech_model=aai.SpeechModel.nano,
                    keyterms_prompt=self.config.get_available_projects()
                )
            elif self.config.assembly_model == 'slam':
                config = aai.TranscriptionConfig(
                    language_code=self.config.language_code, 
                    speech_model=aai.SpeechModel.slam_1,
                    keyterms_prompt=self.config.get_available_projects()
                )
            else:
                # Default to slam if unknown model specified
                print(f"⚠️ Unknown AssemblyAI model '{self.config.assembly_model}', defaulting to slam_1")
                config = aai.TranscriptionConfig(
                    language_code=self.config.language_code, 
                    speech_model=aai.SpeechModel.slam_1,
                    keyterms_prompt=self.config.get_available_projects()
                )
                
            # Create transcriber and transcribe
            transcriber = aai.Transcriber(config=config)
            print("📤 Uploading audio to AssemblyAI...")
            transcript = transcriber.transcribe(str(audio_path))
            
            # Check for errors
            if transcript.status == "error":
                raise Exception(f"AssemblyAI transcription failed: {transcript.error}")
            
            print("✓ AssemblyAI transcription completed")
            
            # Format segments similar to Whisper output
            segments = []
            if hasattr(transcript, 'utterances') and transcript.utterances:
                segments = [u.text for u in transcript.utterances]
            else:
                # If no utterances, just use the full text as a single segment
                segments = [transcript.text]
            
            return {
                'text': transcript.text,
                'language': self.config.language_code,  # AssemblyAI doesn't return language
                'segments': segments
            }
            
        except Exception as e:
            raise Exception(f"AssemblyAI transcription failed: {e}")
    
    def delete_audio_file(self, audio_path):
        """Delete processed audio file"""
        try:
            audio_path = Path(audio_path)
            if audio_path.exists():
                audio_path.unlink()
                print(f"✓ Deleted audio file: {audio_path.name}")
                return True
            return False
        except Exception as e:
            print(f"✗ Failed to delete audio file: {e}")
            return False