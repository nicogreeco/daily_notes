import pyaudio
import wave
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import keyboard

class AudioRecorder: 
    def __init__(self, 
                 sample_rate: int = 44100,
                 channels: int = 1,
                 chunk_size: int = 1024,
                 audio_format: int = pyaudio.paInt16):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.audio_format = audio_format
        
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
        self.frames = []
        self.stream = None
        
        # Use default device by default
        self.selected_device_id = None
        self.default_device_tested = False
        
    def get_available_devices(self) -> List[Tuple[int, str, int]]:
        """Get list of available input audio devices"""
        devices = []
        
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            
            # Only include input devices
            if device_info['maxInputChannels'] > 0:
                devices.append((
                    i,
                    device_info['name'],
                    device_info['maxInputChannels']
                ))
        
        return devices
    
    def get_default_input_device(self) -> dict:
        """Get default input device info"""
        try:
            return self.audio.get_default_input_device_info()
        except OSError:
            return None


    def test_default_device(self) -> bool:
        """Test if default device works"""
        if self.default_device_tested:
            return True
            
        try:
            test_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            # Try to read a small amount of data
            test_stream.read(self.chunk_size)
            test_stream.stop_stream()
            test_stream.close()
            
            self.default_device_tested = True
            return True
            
        except Exception as e:
            print(f"⚠️  Default audio device test failed: {e}")
            return False
    
    def select_device(self) -> Optional[int]:
        """Interactive device selection (only when needed)"""
        devices = self.get_available_devices()
        
        if not devices:
            print("❌ No input devices found!")
            return None
        
        # Show current default device info
        default_device = self.get_default_input_device()
        if default_device:
            print(f"\n🎤 Current default device: {default_device['name']}")
        
        print("\n🎤 Available Audio Input Devices:")
        print("-" * 50)
        
        for i, (device_id, name, channels) in enumerate(devices):
            # Highlight likely headset/microphone devices
            indicator = "🎧" if any(keyword in name.lower() for keyword in 
                                   ['headset', 'microphone', 'mic', 'usb', 'wireless']) else "🔊"
            # Mark default device
            default_mark = " (DEFAULT)" if default_device and device_id == default_device['index'] else ""
            print(f"{i + 1}. {indicator} {name}{default_mark} (ID: {device_id}, Channels: {channels})")
        
        print(f"{len(devices) + 1}. ⚙️  Keep using system default")
        
        while True:
            try:
                choice = input(f"\nSelect device (1-{len(devices) + 1}): ").strip()
                
                if choice == str(len(devices) + 1):
                    return None  # Keep using default device
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(devices):
                    selected_device = devices[choice_idx]
                    print(f"✅ Selected: {selected_device[1]}")
                    return selected_device[0]
                else:
                    print(f"❌ Please enter a number between 1 and {len(devices) + 1}")
            except ValueError:
                print("❌ Please enter a valid number")
    
    def test_device(self, device_id: Optional[int] = None) -> bool:
        """Test if device can record audio"""
        try:
            test_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_id,
                frames_per_buffer=self.chunk_size
            )
            
            # Try to read a small amount of data
            test_stream.read(self.chunk_size)
            test_stream.stop_stream()
            test_stream.close()
            return True
            
        except Exception as e:
            print(f"❌ Device test failed: {e}")
            return False
    
    def start_recording(self, device_id: Optional[int] = None) -> bool:
        """Start recording audio"""
        if self.is_recording:
            print("❌ Already recording!")
            return False
        
        # Use provided device_id or fall back to selected/default
        recording_device = device_id if device_id is not None else self.selected_device_id
        
        try:
            # Test device if not default and not previously tested
            if recording_device is not None and not self.test_device(recording_device):
                return False
            elif recording_device is None and not self.test_default_device():
                print("❌ Default audio device not available. Please select a different device.")
                return False
            
            self.frames = []
            self.stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=recording_device,
                frames_per_buffer=self.chunk_size
            )
            
            self.is_recording = True
            
            # Show which device is being used
            if recording_device is None:
                device_name = "System Default"
                default_device = self.get_default_input_device()
                if default_device:
                    device_name = f"System Default ({default_device['name']})"
            else:
                devices = self.get_available_devices()
                device_name = next((name for id, name, _ in devices if id == recording_device), 
                                 f"Device ID {recording_device}")
            
            print(f"🔴 Recording started using: {device_name}")
            print("Press SPACE to stop or Ctrl+C to cancel...")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
            return False
    
    def _record_audio_thread(self):
        """Background thread for audio recording"""
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
            except Exception as e:
                print(f"❌ Recording error: {e}")
                break
    
    def record_with_hotkey(self, device_id: Optional[int] = None) -> bool:
        """Record audio with spacebar to stop"""
        if not self.start_recording(device_id):
            return False
        
        # Start recording thread
        recording_thread = threading.Thread(target=self._record_audio_thread)
        recording_thread.daemon = True
        recording_thread.start()
        
        # Wait for spacebar press
        try:
            while self.is_recording:
                if keyboard.is_pressed('space'):
                    print("\n⏹️  Stopping recording...")
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n❌ Recording cancelled!")
            self.stop_recording()
            return False
        
        self.stop_recording()
        return True
    
    def stop_recording(self) -> bool:
        """Stop recording"""
        if not self.is_recording:
            print("❌ Not currently recording!")
            return False
        
        self.is_recording = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        
        duration = len(self.frames) * self.chunk_size / self.sample_rate
        print(f"✅ Recording stopped! Duration: {duration:.2f} seconds")
        return True
    
    def save_recording(self, output_path: Path) -> bool:
        """Save recorded audio to file"""
        if not self.frames:
            print("❌ No audio data to save!")
            return False
        
        try:
            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save as WAV file
            with wave.open(str(output_path), 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.audio.get_sample_size(self.audio_format))
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(b''.join(self.frames))
            
            file_size = output_path.stat().st_size / 1024  # KB
            print(f"✅ Audio saved: {output_path.name} ({file_size:.1f} KB)")
            return True
            
        except Exception as e:
            print(f"❌ Failed to save audio: {e}")
            return False
    
    def record_and_save(self, 
                       output_dir: Path, 
                       filename: Optional[str] = None,
                       device_id: Optional[int] = None) -> Optional[Path]:
        """Complete recording workflow"""
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"voice_note_{timestamp}.wav"
        
        # Ensure .wav extension
        if not filename.endswith('.wav'):
            filename += '.wav'
        
        output_path = output_dir / filename
        
        # Use provided device_id, otherwise use selected device or default
        recording_device = device_id if device_id is not None else self.selected_device_id
        
        # Record audio
        if not self.record_with_hotkey(recording_device):
            return None
        
        # Save audio
        if self.save_recording(output_path):
            return output_path
        
        return None
    
    def cleanup(self):
        """Clean up audio resources"""
        if self.is_recording:
            self.stop_recording()
        
        if self.audio:
            self.audio.terminate()