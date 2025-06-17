import os
import tempfile
import subprocess
from pathlib import Path
try:
    from faster_whisper import WhisperModel, BatchedInferencePipeline
except:
    print("Whisper module not found, only assemblyAi mode available")
    
import assemblyai as aai
from mutagen import File as MutagenFile
import wave

class AudioProcessor:
    def __init__(self, config):
        self.config = config
        self.whisper_model = None
        
        # Configure AssemblyAI if needed
        if self.config.audio_model == 'assembly' and self.config.assembly_api_key:
            aai.settings.api_key = self.config.assembly_api_key
        
        # Whisper model will be loaded on-demand
    def _load_whisper_model(self):
        """Load Whisper model on-demand (lazy loading)"""
        if self.whisper_model is not None:
            # Model already loaded
            return self.whisper_model
        
        if self.config.audio_model == 'assembly':
            print(f"Using AssemblyAI model '{self.config.assembly_model}'...")
            
            # No loading needed for AssemblyAI
            print("✓ AssemblyAI configured")
            return None

        elif self.config.audio_model == 'whisper':
            print(f"Loading Whisper model '{self.config.whisper_model}'...")
            try:
                model = WhisperModel(
                    self.config.whisper_model,
                    device="auto",
                    compute_type=self.config.compute_type,
                    cpu_threads=self.config.cpu_threads,
                    num_workers=self.config.num_workers
                )
                self.whisper_model = BatchedInferencePipeline(model=model)
                print("✓ Whisper model loaded successfully")
                return self.whisper_model
            except Exception as e:
                print(f"✗ Failed to load Whisper model: {e}")
                raise
    
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
                    return False, "Unable to determine duration (no ffprobe and unsupported by Mutagen)"

            # Check duration limits
            if duration < min_duration:
                return False, f"Audio too short: {duration:.1f}s (minimum: {min_duration}s)"
            if duration > max_duration:
                return False, f"Audio too long: {duration:.1f}s (maximum: {max_duration}s)"

            return True, f"Valid audio file: {duration:.1f}s"
    
    def normalize_audio(self, input_path):
        """Convert audio to optimal format for Whisper"""
        try:
            # Create temporary file for normalized audio
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            temp_path = temp_file.name
            temp_file.close()
            
            # FFmpeg command to normalize audio
            cmd = [
                'ffmpeg', '-y', '-i', str(input_path),
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-avoid_negative_ts', 'make_zero',
                temp_path
            ]
            
            # Run FFmpeg with suppressed output
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                os.unlink(temp_path) if os.path.exists(temp_path) else None
                raise Exception(f"FFmpeg error: {result.stderr}")
            
            return temp_path
            
        except subprocess.TimeoutExpired:
            os.unlink(temp_path) if os.path.exists(temp_path) else None
            raise Exception("Audio normalization timeout")
        except FileNotFoundError:
            raise Exception("FFmpeg not found. Please install FFmpeg")
        except Exception as e:
            os.unlink(temp_path) if os.path.exists(temp_path) else None
            raise Exception(f"Audio normalization failed: {e}")
    
    def transcribe(self, audio_path):
        """Transcribe audio file using configured service"""
        print(f"Transcribing: {Path(audio_path).name}")
        
        # Validate audio first
        is_valid, message = self.validate_audio(audio_path)
        if not is_valid:
            raise Exception(f"Audio validation failed: {message}")
        
        # print(f"✓ Audio validation passed: {message}")
        
        # AssemblyAI doesn't need normalization, so handle it separately
        if self.config.audio_model == 'assembly':
            return self._transcribe_with_assembly(audio_path)
        
        # For Whisper, continue with normalization
        print("Normalizing audio for optimal transcription...")
        normalized_path = None
        
        try:
            normalized_path = self.normalize_audio(audio_path)
            print("✓ Audio normalized")
            
            # Lazy-load Whisper model if needed
            if self.whisper_model is None:
                self._load_whisper_model()

            # Transcribe using Whisper
            print("Starting transcription...")
            if self.config.audio_model == 'whisper':
                segments, info = self.whisper_model.transcribe(
                    normalized_path, 
                    batch_size=self.config.batch_size, 
                    language=self.config.language_code, 
                    log_progress=True, 
                    word_timestamps=False,
                    beam_size=self.config.beam_size
                )
                segments = list(segments)  # The transcription will actually run here.
                segments_text = [segment.text for segment in segments]
                
                print("✓ Transcription completed")
            
                return {
                    'text': ' '.join(segments_text),
                    'language': info.language,
                    'segments': segments_text
                }
            
        except Exception as e:
            raise Exception(f"Transcription failed: {e}")
        
        finally:
            # Clean up temporary normalized file
            if normalized_path and os.path.exists(normalized_path):
                try:
                    os.unlink(normalized_path)
                except:
                    pass  # Ignore cleanup errors
    
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