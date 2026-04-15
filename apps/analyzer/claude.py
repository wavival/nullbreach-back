import json

import anthropic
from django.conf import settings

SYSTEM_PROMPT = (
    "You are a cybersecurity expert specializing in secure code review. "
    "Analyze the provided code snippet for vulnerabilities based on the OWASP Top 10. "
    "Return ONLY a valid JSON object — no markdown, no prose — with this exact structure:\n"
    "{\n"
    '  "vulnerabilities": [\n'
    "    {\n"
    '      "id": "A01:2021",\n'
    '      "name": "Broken Access Control",\n'
    '      "severity": "critical|high|medium|low|info",\n'
    '      "line": <line number or null>,\n'
    '      "description": "...",\n'
    '      "recommendation": "..."\n'
    "    }\n"
    "  ],\n"
    '  "summary": "Overall risk assessment in 1-2 sentences.",\n'
    '  "risk_score": <integer 0-100>\n'
    "}"
)


def analyze_code(code: str, language: str = "") -> dict:
    """
    Send a code snippet to Claude for OWASP Top 10 analysis.
    Returns a parsed dict with vulnerabilities, summary, and risk_score.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_content = f"Language: {language}\n\n```\n{code}\n```" if language else f"```\n{code}\n```"

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if Claude wraps the JSON anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    return json.loads(raw)
