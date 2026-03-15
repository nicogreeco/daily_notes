import json

from openai import OpenAI


def create_llm_client(config):
    """Create an LLM client based on the configured provider."""
    if config.llm_provider == "deepseek":
        return OpenAI(
            api_key=config.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )

    return OpenAI(api_key=config.openai_api_key)


def clean_json_response(content: str) -> str:
    """Remove markdown fences when models wrap JSON in a code block."""
    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return content


def parse_json_response(content, *, response_label, fallback_parser=None, default=None):
    """Parse model JSON with one consistent fallback path."""
    cleaned_content = clean_json_response(content)

    try:
        return json.loads(cleaned_content)
    except json.JSONDecodeError as error:
        print(f"Warning: Could not parse {response_label} response as JSON: {error}")
        if fallback_parser is not None:
            return fallback_parser(content)
        return default
