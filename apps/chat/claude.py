import anthropic
from django.conf import settings

SYSTEM_PROMPT = (
    "You are NullBreach, an expert AI cybersecurity assistant. "
    "You help developers identify vulnerabilities, understand security concepts, "
    "review code for weaknesses, and apply best practices based on OWASP, NIST, "
    "and industry standards. Be precise, technical, and actionable in your responses."
)


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def chat_completion(history: list[dict]) -> str:
    """
    Send conversation history to Claude and return the assistant reply.

    history: list of {"role": "user"|"assistant", "content": str}
    """
    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    return response.content[0].text
