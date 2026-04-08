"""Shared Claude API client with error handling for all analyzers."""

from __future__ import annotations

import json
import logging

import anthropic

MODEL = "claude-sonnet-4-6"
logger = logging.getLogger(__name__)


def call_claude(client: anthropic.Anthropic, system: str, user: str, max_retries: int = 1) -> dict:
    """Send a structured extraction prompt to Claude and parse the JSON response.

    Handles markdown code blocks, JSON parse errors, and API failures.
    Returns a dict with an "error" key on failure instead of crashing.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = response.content[0].text

            # Extract JSON from markdown code blocks
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]

            return json.loads(text.strip())

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning("Claude returned non-JSON on attempt %d: %s", attempt + 1, last_error)
        except anthropic.APIError as e:
            last_error = f"API error: {e}"
            logger.warning("Claude API error on attempt %d: %s", attempt + 1, last_error)

    return {"error": last_error, "_raw_response": text if "text" in dir() else None}
