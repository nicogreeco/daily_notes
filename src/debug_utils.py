from pathlib import Path
from datetime import datetime
import json
from typing import Dict, Any, Optional

class DebugLogger:
    """Utility class for logging LLM conversations for debugging"""
    
    @staticmethod
    def save_llm_conversation(config, source_type: str, model: str, temperature: float, 
                             messages: list, response: str, metadata: Dict[str, Any] = None,
                             reference_id: Optional[str] = None):
        """
        Save LLM conversation for debugging
        
        Args:
            config: Application configuration
            source_type: Type of conversation (daily_note, todo, weekly)
            model: LLM model used
            temperature: Temperature setting
            messages: The messages sent to the LLM
            response: The LLM response
            metadata: Additional metadata to save
            reference_id: ID to link to the source note
        """
        if not config.debug_llm:
            return
            
        # Create debug folder
        debug_folder = config.daily_notes_path / config.debug_folder
        debug_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if reference_id:
            filename = f"{timestamp}_{source_type}_{reference_id}.md"
        else:
            filename = f"{timestamp}_{source_type}.md"
        
        debug_file = debug_folder / filename
        
        # TODO improve this token calculation
        # Calculate token count (approximate)
        # This is a very rough estimation; approximately 4 chars per token
        prompt_text = " ".join(msg["content"] for msg in messages)
        prompt_tokens = len(prompt_text) // 4
        response_tokens = len(response) // 4
        total_tokens = prompt_tokens + response_tokens
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
            
        metadata.update({
            'type': source_type,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model': model,
            'temperature': temperature,
            'prompt_tokens_approx': prompt_tokens,
            'response_tokens_approx': response_tokens,
            'total_tokens_approx': total_tokens
        })
        
        if reference_id:
            metadata['reference'] = reference_id
        
        # Write file
        with open(debug_file, 'w', encoding='utf-8') as f:
            # Write YAML frontmatter
            f.write("---\n")
            for key, value in metadata.items():
                f.write(f"{key}: {value}\n")
            f.write("---\n\n")
            
            # Write conversation
            f.write(f"# LLM Conversation Debug: {source_type}\n\n")
            
            # Write messages
            f.write(f"## Messages\n\n")
            for i, msg in enumerate(messages):
                f.write(f"### {i+1}. {msg['role'].upper()}\n\n")
                f.write(f"```\n{msg['content']}\n```\n\n")
            
            # Write response
            f.write(f"## Response\n\n")
            f.write(f"```\n{response}\n```\n\n")
            
            # Try to parse JSON if applicable
            if source_type in ['daily_note', 'todo', 'weekly']:
                f.write(f"## JSON Parsing Check\n\n")
                try:
                    parsed = json.loads(response)
                    f.write("✅ JSON successfully parsed\n\n")
                    f.write("```json\n")
                    f.write(json.dumps(parsed, indent=2))
                    f.write("\n```\n")
                except json.JSONDecodeError as e:
                    f.write(f"❌ JSON parsing failed: {e}\n\n")
                    f.write("Error position visualization:\n\n")
                    f.write("```\n")
                    # Show the context around the error
                    error_pos = e.pos
                    start = max(0, error_pos - 50)
                    end = min(len(response), error_pos + 50)
                    context = response[start:end]
                    marker = ' ' * (min(50, error_pos - start)) + '^ ERROR HERE'
                    f.write(context + '\n' + marker)
                    f.write("\n```\n")
        
        return debug_file