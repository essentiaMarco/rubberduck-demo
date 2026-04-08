"""Shared Claude API client with retry, circuit breaker, and backoff."""

from __future__ import annotations

import json
import logging
import time
import random
import threading

import anthropic

MODEL = "claude-opus-4-6"
logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 529}

# ---------------------------------------------------------------------------
# Circuit breaker — stop hammering the API after repeated 529s
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_consecutive_529s = 0
_CIRCUIT_BREAKER_THRESHOLD = 3
_CIRCUIT_BREAKER_COOLDOWN = 120  # seconds
_circuit_open_until: float = 0.0


def _check_circuit() -> str | None:
    """Return an error message if the circuit breaker is open, else None."""
    global _circuit_open_until
    with _lock:
        if _consecutive_529s >= _CIRCUIT_BREAKER_THRESHOLD:
            remaining = _circuit_open_until - time.time()
            if remaining > 0:
                return f"Circuit breaker open: API overloaded. Retry in {remaining:.0f}s."
            # Cooldown expired — half-open, allow one attempt
    return None


def _record_529():
    """Record a 529 failure."""
    global _consecutive_529s, _circuit_open_until
    with _lock:
        _consecutive_529s += 1
        if _consecutive_529s >= _CIRCUIT_BREAKER_THRESHOLD:
            _circuit_open_until = time.time() + _CIRCUIT_BREAKER_COOLDOWN
            logger.warning(
                "Circuit breaker OPEN after %d consecutive 529s. Cooling down %ds.",
                _consecutive_529s, _CIRCUIT_BREAKER_COOLDOWN,
            )


def _record_success():
    """Reset the circuit breaker on a successful call."""
    global _consecutive_529s, _circuit_open_until
    with _lock:
        _consecutive_529s = 0
        _circuit_open_until = 0.0


# ---------------------------------------------------------------------------
# Main API call function
# ---------------------------------------------------------------------------


def call_claude(client: anthropic.Anthropic, system: str, user: str, max_retries: int = 4) -> dict:
    """Send a structured extraction prompt to Claude and parse the JSON response.

    Features:
    - Retries with exponential backoff + jitter on transient errors (429, 529)
    - Longer backoff for 529 (overloaded) vs 429 (rate limit)
    - Circuit breaker: stops retrying after 3 consecutive 529s across all calls
    - Fails immediately on permanent errors (401, 403, 404)
    - Returns a dict with an "error" key on exhaustion
    """
    # Check circuit breaker before even trying
    circuit_err = _check_circuit()
    if circuit_err:
        logger.warning("Circuit breaker rejected call: %s", circuit_err)
        return {"error": circuit_err}

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

            result = json.loads(text.strip())
            _record_success()
            return result

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning("Claude returned non-JSON on attempt %d: %s", attempt + 1, last_error)

        except anthropic.APIStatusError as e:
            last_error = f"API error {e.status_code}: {e.message}"
            if e.status_code not in RETRYABLE_STATUS_CODES:
                logger.error("Permanent API error (no retry): %s", last_error)
                break
            if e.status_code == 529:
                _record_529()
                # Check if circuit breaker just tripped
                circuit_err = _check_circuit()
                if circuit_err:
                    logger.warning("Circuit breaker tripped mid-retry: %s", circuit_err)
                    return {"error": circuit_err}
            logger.warning("Retryable API error on attempt %d: %s", attempt + 1, last_error)

        except anthropic.APIError as e:
            last_error = f"API error: {e}"
            logger.warning("Claude API error on attempt %d: %s", attempt + 1, last_error)

        # Exponential backoff — longer for 529 (server overload) than 429 (rate limit)
        if attempt < max_retries:
            if "529" in str(last_error):
                delay = min(2 ** (attempt + 2) + random.uniform(0, 5), 120)
            else:
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
            logger.info("Retrying in %.1fs (attempt %d/%d)...", delay, attempt + 1, max_retries)
            time.sleep(delay)

    return {"error": last_error, "_raw_response": text}
