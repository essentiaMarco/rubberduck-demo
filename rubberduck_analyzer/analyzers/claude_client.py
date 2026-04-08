"""Shared Claude API client with retry + exponential backoff for all analyzers."""

from __future__ import annotations

import json
import logging
import time
import random

import anthropic

MODEL = "claude-sonnet-4-6"
logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 529}


def call_claude(client: anthropic.Anthropic, system: str, user: str, max_retries: int = 4) -> dict:
    """Send a structured extraction prompt to Claude and parse the JSON response.

    Retries with exponential backoff + jitter on transient errors (429, 529).
    Fails immediately on permanent errors (401, 403, 404).
    Returns a dict with an "error" key on exhaustion instead of crashing.
    """
    last_error = None
    text = None
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

        except anthropic.APIStatusError as e:
            last_error = f"API error {e.status_code}: {e.message}"
            if e.status_code not in RETRYABLE_STATUS_CODES:
                logger.error("Permanent API error (no retry): %s", last_error)
                break
            logger.warning("Retryable API error on attempt %d: %s", attempt + 1, last_error)

        except anthropic.APIError as e:
            last_error = f"API error: {e}"
            logger.warning("Claude API error on attempt %d: %s", attempt + 1, last_error)

        # Exponential backoff with jitter before next attempt
        if attempt < max_retries:
            delay = min(2 ** attempt + random.uniform(0, 1), 30)
            logger.info("Retrying in %.1fs (attempt %d/%d)...", delay, attempt + 1, max_retries)
            time.sleep(delay)

    return {"error": last_error, "_raw_response": text}
