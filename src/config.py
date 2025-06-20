import os
import yaml
from pathlib import Path
from typing import Dict, List

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.script_dir = Path(__file__).parent.parent  # daily_notes_script folder
        self.config_dir = self.script_dir / "config"  # Config directory
        self.main_dir = self.script_dir.parent  # main_folder
        
        # Load or create configuration
        self.config_data = self._load_or_create_config()
        
        # Load API keys
        self.openai_api_key = self._load_api_key("openai")
        self.assembly_api_key = self._load_api_key("assembly")
        self.deepseek_api_key = self._load_api_key("deepseek")

    def _load_api_key(self, service: str) -> str:
        """Load API key from separate file"""
        api_key_file = self.config_dir / f"{service}_api_key.txt"
        
        if not api_key_file.exists():
            print(f"{service.title()} API key file not found at {api_key_file}")
            print(f"Please create config/{service}_api_key.txt with your {service.title()} API key")
            return ""
        
        try:
            with open(api_key_file, 'r', encoding='utf-8') as f:
                api_key = f.read().strip()
                
            if not api_key or api_key == f"your_{service}_api_key_here":
                print(f"Please add your actual {service.title()} API key to config/{service}_api_key.txt")
                return ""
                
            return api_key
        except Exception as e:
            print(f"Error reading {service.title()} API key: {e}")
            return ""

    
    def _load_or_create_config(self) -> Dict:
        """Load existing config or create default one"""
        # Make sure config directory exists
        self.config_dir.mkdir(exist_ok=True)

        config_file = self.config_dir / self.config_path
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            # Create default config
            default_config = self._get_default_config()
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False, indent=2)
            print(f"Created default configuration at {config_file}")
            return default_config
        
    def _get_default_config(self) -> Dict:
        """Generate default configuration"""
        return {
            'project': {
                'name': 'MyCurrentProject',
                'vault_path': '../ObsidianVault',
                'daily_notes_path': '../Daily',
                'projects_path': '../Projects'
            },
            'audio': {
                'input_folder': 'AudioInbox',
                'supported_formats': ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'],
                'max_duration_seconds': 1800,  # 30 minutes
                'min_duration_seconds': 5,     # 5 seconds
                'delete_after_processing': True
            },
            'processing': {
                'whisper_model': 'base',  # base, small, medium, large
                'llm_provider': 'openai',  # Options: openai, deepseek
                'model': 'gpt-4.1-mini',    # Model name for chosen provider
                'weekly_summary_model': 'gpt-4.1', # Model for weekly summaries
                'temperature': 0.3,
                'max_tokens': 2000,
                'audio_model': 'whisper',
                'batch_size': 16,
                'beam_size': 5,
                'language_code': 'en',
                'compute_type': 'float32',
                'cpu_threads': 4,
                'num_workers': 2,
                'assembly_model': 'slam',
                'track_completed_todos': True  # New option to track completed todos in weekly summaries
            },
            'output': {
                'date_format': '%Y-%m-%d',
                'include_audio_filename': True,
                'include_processing_timestamp': True,
                'save_transcript': True,  # Enable transcript saving by default
                'transcript_folder': 'transcripts'  # Default folder name
            }
        }
            
    def get_available_projects(self) -> List[str]:
        """Get list of available projects from projects folder"""
        available_projects = []
        
        if not self.projects_path.exists():
            print(f"Projects path not found: {self.projects_path}")
            return []
        
        for item in self.projects_path.iterdir():
            if item.is_dir() and item.name != "Daily Notes":
                available_projects.append(item.name)
        
        return sorted(available_projects)
    
    
    # Properties for easy access to configuration values
    @property
    def project_name(self) -> str:
        return self.config_data['project']['name']
    
    @property
    def vault_path(self) -> Path:
        return self.main_dir / self.config_data['project']['vault_path']
    
    @property
    def daily_notes_path(self) -> Path:
        return self.main_dir / self.config_data['project']['daily_notes_path']
    
    @property
    def projects_path(self) -> Path:
        return self.main_dir / self.config_data['project']['projects_path']
    
    @property
    def audio_input_path(self) -> Path:
        return self.script_dir / self.config_data['audio']['input_folder']
    
    @property
    def supported_formats(self) -> List[str]:
        return self.config_data['audio']['supported_formats']
    
    @property
    def max_duration(self) -> int:
        return self.config_data['audio']['max_duration_seconds']
    
    @property
    def min_duration(self) -> int:
        return self.config_data['audio']['min_duration_seconds']
    
    @property
    def delete_after_processing(self) -> bool:
        return self.config_data['audio']['delete_after_processing']
    
    @property
    def whisper_model(self) -> str:
        return self.config_data['processing']['whisper_model']
    
    @property
    def audio_model(self) -> str:
        return self.config_data['processing'].get('audio_model', 'whisper')
    
    @property
    def batch_size(self) -> int:
        return self.config_data['processing'].get('batch_size', 16)
    
    @property
    def beam_size(self) -> int:
        return self.config_data['processing'].get('beam_size', 5)

    @property
    def track_completed_todos(self) -> bool:
        return self.config_data['processing'].get('track_completed_todos', True)

    @property
    def language_code(self) -> str:
        return self.config_data['processing'].get('language_code', 'en')
    
    @property
    def llm_provider(self) -> str:
        return self.config_data['processing'].get('llm_provider', 'openai')

    @property
    def gpt_model(self) -> str:
        return self.config_data['processing'].get('model', 'gpt-4o-mini')

    @property
    def weekly_summary_model(self) -> str:
        return self.config_data['processing'].get('weekly_summary_model', self.gpt_model)
    
    @property
    def temperature(self) -> float:
        return self.config_data['processing']['temperature']
    
    @property
    def max_tokens(self) -> int:
        return self.config_data['processing']['max_tokens']

    @property
    def save_transcript(self) -> bool:
        return self.config_data['output'].get('save_transcript', False)

    @property
    def transcript_folder(self) -> str:
        return self.config_data['output'].get('transcript_folder', 'transcripts')
    
    @property
    def compute_type(self) -> str:
        return self.config_data['processing'].get('compute_type', 'float32')

    @property
    def cpu_threads(self) -> int:
        return self.config_data['processing'].get('cpu_threads', 4)
    
    @property
    def num_workers(self) -> int:
        return self.config_data['processing'].get('num_workers', 2)
    
    @property
    def assembly_model(self) -> str:
        return self.config_data['processing'].get('assembly_model', 'slam')
        
    def validate_config(self) -> bool:
        """Validate configuration and paths"""
        if not self.openai_api_key:
            print("❌ OpenAI API key not configured")
            return False
        
        if self.audio_model == 'assembly' and not self.assembly_api_key:
            print("❌ AssemblyAI API key not configured but 'assembly' is selected as audio model")
            return False
        
        if not self.audio_input_path.exists():
            print(f"❌ Audio input folder not found: {self.audio_input_path}")
            return False
        
        print("✅ Configuration valid")
        return True
    
    def print_config_summary(self):
        """Print configuration summary"""
        print("\n📋 Configuration Summary:")
        print(f"  Project: {self.project_name}")
        print(f"  Vault: {self.vault_path}")
        print(f"  Daily Notes: {self.daily_notes_path}")
        print(f"  Audio Inbox: {self.audio_input_path}")
        print(f"  Whisper Model: {self.whisper_model}")
        print(f"  GPT Model: {self.gpt_model}")
        print(f"  Delete Audio After Processing: {self.delete_after_processing}")