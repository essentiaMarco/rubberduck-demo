"""Secret and credential scanner for digital forensic investigations.

Detects passwords, API keys, private keys, crypto wallet addresses,
tokens, 2FA recovery codes, and other sensitive data in evidence text.

Uses pattern-based regex matching and Shannon entropy analysis.
Output format matches regex_extractors.extract_all() for seamless
integration into the entity extraction pipeline.
"""

import math
import re
from dataclasses import dataclass
from typing import Any

from rubberduck.entities.regex_extractors import _safe_finditer

# ── Secret pattern definitions ───────────────────────────────


@dataclass(frozen=True)
class SecretPattern:
    name: str
    pattern: re.Pattern
    entity_type: str  # credential, crypto_wallet, api_key, private_key, token
    secret_type: str  # aws_access_key, btc_address, etc.
    severity: str  # critical, high, medium, low
    confidence: float
    description: str


# Compile all patterns once at module load

_PATTERNS: list[SecretPattern] = [
    # ── Cloud API keys (critical) ────────────────────────────
    SecretPattern(
        name="AWS Access Key",
        pattern=re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"),
        entity_type="api_key", secret_type="aws_access_key",
        severity="critical", confidence=0.95,
        description="AWS IAM access key ID",
    ),
    SecretPattern(
        name="AWS Secret Key",
        pattern=re.compile(
            r"(?i)(?:aws_secret_access_key|aws_secret|secret_key)\s*[:=]\s*['\"]?"
            r"([A-Za-z0-9/+=]{40})"
        ),
        entity_type="api_key", secret_type="aws_secret_key",
        severity="critical", confidence=0.90,
        description="AWS secret access key",
    ),
    SecretPattern(
        name="GCP API Key",
        pattern=re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z\-_]{35}(?![A-Za-z0-9])"),
        entity_type="api_key", secret_type="gcp_api_key",
        severity="critical", confidence=0.90,
        description="Google Cloud Platform API key",
    ),
    SecretPattern(
        name="Azure Storage Key",
        pattern=re.compile(
            r"(?i)AccountKey\s*=\s*([A-Za-z0-9/+=]{86,88})"
        ),
        entity_type="api_key", secret_type="azure_storage_key",
        severity="critical", confidence=0.90,
        description="Azure storage account key",
    ),
    # ── Payment keys (critical) ──────────────────────────────
    SecretPattern(
        name="Stripe Secret Key",
        pattern=re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
        entity_type="api_key", secret_type="stripe_secret_key",
        severity="critical", confidence=0.95,
        description="Stripe live secret API key",
    ),
    SecretPattern(
        name="Stripe Publishable Key",
        pattern=re.compile(r"pk_live_[0-9a-zA-Z]{24,}"),
        entity_type="api_key", secret_type="stripe_publishable_key",
        severity="high", confidence=0.95,
        description="Stripe live publishable API key",
    ),
    # ── Crypto wallets (high) ────────────────────────────────
    SecretPattern(
        name="Bitcoin Address (P2PKH/P2SH)",
        # Require exactly 25-34 Base58Check chars after the leading 1 or 3.
        # Negative lookbehind/ahead for alphanumerics AND slashes/dots to
        # avoid matching SHA256 hashes in file paths like /ab12/ab12cd...
        pattern=re.compile(r"(?<![A-Za-z0-9/.])[13][a-km-zA-HJ-NP-Z1-9]{25,34}(?![A-Za-z0-9/.])"),
        entity_type="crypto_wallet", secret_type="btc_address",
        severity="high", confidence=0.85,
        description="Bitcoin address (legacy P2PKH or P2SH format)",
    ),
    SecretPattern(
        name="Bitcoin Address (Bech32)",
        pattern=re.compile(r"(?<![A-Za-z0-9])bc1[a-zA-HJ-NP-Z0-9]{25,62}(?![A-Za-z0-9])"),
        entity_type="crypto_wallet", secret_type="btc_bech32",
        severity="high", confidence=0.90,
        description="Bitcoin address (native SegWit bech32 format)",
    ),
    SecretPattern(
        name="Ethereum Address",
        pattern=re.compile(r"(?<![A-Za-z0-9])0x[0-9a-fA-F]{40}(?![A-Za-z0-9])"),
        entity_type="crypto_wallet", secret_type="eth_address",
        severity="high", confidence=0.90,
        description="Ethereum wallet address",
    ),
    SecretPattern(
        name="Monero Address",
        pattern=re.compile(r"(?<![A-Za-z0-9])4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}(?![A-Za-z0-9])"),
        entity_type="crypto_wallet", secret_type="xmr_address",
        severity="high", confidence=0.90,
        description="Monero wallet address",
    ),
    SecretPattern(
        name="Litecoin Address",
        pattern=re.compile(r"(?<![A-Za-z0-9/.])[LM3][a-km-zA-HJ-NP-Z1-9]{26,33}(?![A-Za-z0-9/.])"),
        entity_type="crypto_wallet", secret_type="ltc_address",
        severity="high", confidence=0.80,
        description="Litecoin wallet address",
    ),
    # ── Private keys (critical) ──────────────────────────────
    SecretPattern(
        name="RSA Private Key",
        pattern=re.compile(r"-----BEGIN RSA PRIVATE KEY-----"),
        entity_type="private_key", secret_type="rsa_private_key",
        severity="critical", confidence=0.99,
        description="RSA private key (PEM format)",
    ),
    SecretPattern(
        name="SSH Private Key",
        pattern=re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"),
        entity_type="private_key", secret_type="ssh_private_key",
        severity="critical", confidence=0.99,
        description="OpenSSH private key",
    ),
    SecretPattern(
        name="PGP Private Key",
        pattern=re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----"),
        entity_type="private_key", secret_type="pgp_private_key",
        severity="critical", confidence=0.99,
        description="PGP/GPG private key block",
    ),
    SecretPattern(
        name="EC Private Key",
        pattern=re.compile(r"-----BEGIN EC PRIVATE KEY-----"),
        entity_type="private_key", secret_type="ec_private_key",
        severity="critical", confidence=0.99,
        description="Elliptic Curve private key",
    ),
    SecretPattern(
        name="PKCS8 Private Key",
        pattern=re.compile(r"-----BEGIN PRIVATE KEY-----"),
        entity_type="private_key", secret_type="pkcs8_private_key",
        severity="critical", confidence=0.99,
        description="PKCS#8 private key (generic format)",
    ),
    # ── Auth tokens (high) ───────────────────────────────────
    SecretPattern(
        name="JWT Token",
        pattern=re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        entity_type="token", secret_type="jwt_token",
        severity="high", confidence=0.90,
        description="JSON Web Token",
    ),
    SecretPattern(
        name="GitHub Token (new)",
        pattern=re.compile(r"gh[ps]_[A-Za-z0-9_]{36,}"),
        entity_type="token", secret_type="github_token",
        severity="high", confidence=0.95,
        description="GitHub personal access token or secret",
    ),
    SecretPattern(
        name="GitHub Token (classic)",
        pattern=re.compile(r"ghp_[A-Za-z0-9_]{36}"),
        entity_type="token", secret_type="github_classic_token",
        severity="high", confidence=0.95,
        description="GitHub classic personal access token",
    ),
    SecretPattern(
        name="Slack Token",
        pattern=re.compile(r"xox[bpras]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}"),
        entity_type="token", secret_type="slack_token",
        severity="high", confidence=0.95,
        description="Slack API token (bot, user, or app)",
    ),
    SecretPattern(
        name="Discord Token",
        pattern=re.compile(r"[MN][A-Za-z\d]{23,}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"),
        entity_type="token", secret_type="discord_token",
        severity="high", confidence=0.85,
        description="Discord bot or user token",
    ),
    # ── Database connection strings (critical) ───────────────
    SecretPattern(
        name="Database Connection String",
        pattern=re.compile(
            r"(?:mysql|postgres|postgresql|mongodb|redis|amqp|mssql)"
            r"(?:\+\w+)?://[^:]+:[^@\s]+@[^\s]+"
        ),
        entity_type="credential", secret_type="db_connection_string",
        severity="critical", confidence=0.90,
        description="Database connection string with embedded password",
    ),
    # ── Passwords in plaintext (high) ────────────────────────
    SecretPattern(
        name="Password Assignment",
        pattern=re.compile(
            r"(?i)(?:password|passwd|pwd|pass|secret|token|api_key|apikey|auth)"
            r"\s*[:=]\s*['\"]([^'\"\s]{4,})['\"]",
        ),
        entity_type="credential", secret_type="plaintext_password",
        severity="high", confidence=0.75,
        description="Password or secret in plaintext assignment",
    ),
    SecretPattern(
        name="Password in URL",
        pattern=re.compile(
            r"https?://[^:]+:([^@\s]+)@[^\s]+"
        ),
        entity_type="credential", secret_type="password_in_url",
        severity="high", confidence=0.85,
        description="Password embedded in URL",
    ),
    # ── WiFi passwords ───────────────────────────────────────
    SecretPattern(
        name="WiFi PSK",
        pattern=re.compile(r"(?i)(?:psk|wpa_passphrase|wifi_password|network_key)\s*[:=]\s*['\"]?([^\s'\"]{8,63})"),
        entity_type="credential", secret_type="wifi_psk",
        severity="medium", confidence=0.80,
        description="WiFi pre-shared key / WPA password",
    ),
    # ── 2FA / Recovery codes (high) ──────────────────────────
    SecretPattern(
        name="TOTP Secret",
        pattern=re.compile(
            r"(?i)(?:totp|2fa|authenticator|otp_secret|mfa_secret)\s*[:=]\s*['\"]?"
            r"([A-Z2-7]{16,32})"
        ),
        entity_type="credential", secret_type="totp_secret",
        severity="high", confidence=0.85,
        description="TOTP/2FA authenticator secret key (base32)",
    ),
    SecretPattern(
        name="Recovery Code Block",
        pattern=re.compile(
            r"(?i)(?:recovery|backup)\s*(?:codes?|keys?)\s*[:=\n]\s*"
            r"((?:[A-Za-z0-9]{4,8}[- ]?){4,})"
        ),
        entity_type="credential", secret_type="recovery_codes",
        severity="high", confidence=0.80,
        description="2FA/account recovery backup codes",
    ),
    # ── SSH / Server credentials ─────────────────────────────
    SecretPattern(
        name="SSH Password in Config",
        pattern=re.compile(
            r"(?i)(?:ssh_pass|sshpass|IdentityFile|PasswordAuthentication)\s*[:=]\s*['\"]?([^\s'\"]+)"
        ),
        entity_type="credential", secret_type="ssh_credential",
        severity="high", confidence=0.80,
        description="SSH credential in configuration",
    ),
    # ── Generic high-entropy tokens ──────────────────────────
    SecretPattern(
        name="Bearer Token",
        pattern=re.compile(r"(?i)(?:Bearer|Authorization)\s*[:=]?\s*['\"]?([A-Za-z0-9_\-./+=]{32,})['\"]?"),
        entity_type="token", secret_type="bearer_token",
        severity="high", confidence=0.75,
        description="Bearer or Authorization token value",
    ),
    SecretPattern(
        name="Generic API Key Assignment",
        pattern=re.compile(
            r"(?i)(?:api[_-]?key|api[_-]?secret|access[_-]?key|secret[_-]?key)"
            r"\s*[:=]\s*['\"]([A-Za-z0-9_\-./+=]{16,})['\"]"
        ),
        entity_type="api_key", secret_type="generic_api_key",
        severity="high", confidence=0.80,
        description="Generic API key/secret in config or code",
    ),
    # ── Cloud service account (critical) ─────────────────────
    SecretPattern(
        name="GCP Service Account JSON",
        pattern=re.compile(r'"type"\s*:\s*"service_account"'),
        entity_type="api_key", secret_type="gcp_service_account",
        severity="critical", confidence=0.90,
        description="Google Cloud service account key file",
    ),
    # ── Sendgrid / Twilio / common SaaS ─────────────────────
    SecretPattern(
        name="SendGrid API Key",
        pattern=re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
        entity_type="api_key", secret_type="sendgrid_api_key",
        severity="high", confidence=0.95,
        description="SendGrid API key",
    ),
    SecretPattern(
        name="Twilio Account SID",
        pattern=re.compile(r"AC[a-f0-9]{32}"),
        entity_type="api_key", secret_type="twilio_account_sid",
        severity="high", confidence=0.85,
        description="Twilio account SID",
    ),
]


# ── Shannon entropy analysis ────────────────────────────────


def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy in bits per character."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


# Small set of common English words to exclude from entropy detection
_COMMON_WORDS = frozenset({
    "international", "understanding", "communication", "approximately",
    "recommendation", "representative", "administration", "transportation",
    "characteristics", "investigation", "unfortunately", "comprehensive",
    "organizational", "environmental", "infrastructure", "accountability",
    "interpretation", "confidential", "acknowledgement", "authentication",
    "responsibility", "discrimination", "superintendent", "congratulations",
    "transformation", "telecommunications", "implementation", "classification",
    "representations", "extraordinarily", "disappointment", "independently",
})

_ENTROPY_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-./+=]{28,}")
_ENTROPY_THRESHOLD = 5.5
_MIN_TOKEN_LEN = 28

# Patterns that look like secrets but aren't — file hashes, paths, UUIDs, etc.
_FALSE_POSITIVE_RE = re.compile(
    r"(?:"
    r"[0-9a-f]{32,}"  # hex hashes (MD5, SHA1, SHA256)
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"  # UUIDs
    r"|/[a-zA-Z0-9_/.=-]+"  # file paths
    r"|https?://[^\s]+"  # URLs (handled by URL extractor)
    r"|[A-Za-z0-9+/]{40,}={1,2}"  # plain base64 blobs (not contextual secrets)
    r"|data:[a-z]+/[a-z]+"  # data URIs
    r")",
    re.IGNORECASE,
)


def _entropy_scan(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Find high-entropy strings that may be undiscovered secrets.

    Tuned for low false-positive rate: requires length >= 24, entropy >= 5.2,
    and filters out hex hashes, UUIDs, file paths, and base64 blobs.
    Only fires when the token appears near a credential-related keyword.
    """
    results: list[dict[str, Any]] = []

    # Only scan if the text contains at least one credential-like keyword
    _CREDENTIAL_CONTEXT = re.compile(
        r"(?i)(?:password|secret|key|token|auth|credential|api.?key|private|"
        r"access.?key|bearer|signing|encryption|decrypt|passphrase|pin|otp)",
    )
    if not _CREDENTIAL_CONTEXT.search(text):
        return results

    for m in _safe_finditer(_ENTROPY_TOKEN_RE, text):
        token = m.group()
        if len(token) > 200:
            continue  # Skip absurdly long matches
        if len(token) < _MIN_TOKEN_LEN:
            continue
        if token.lower() in _COMMON_WORDS:
            continue
        # Skip known false-positive patterns
        if _FALSE_POSITIVE_RE.fullmatch(token):
            continue
        # Skip if the token is purely hexadecimal (likely a hash)
        if all(c in "0123456789abcdef" for c in token.lower()):
            continue
        # Skip tokens that are predominantly digits (phone numbers, IDs)
        digit_ratio = sum(c.isdigit() for c in token) / len(token)
        if digit_ratio > 0.7:
            continue
        # Require a credential-related keyword within 80 chars (tight proximity)
        context_start = max(0, m.start() - 80)
        context_end = min(len(text), m.end() + 80)
        context = text[context_start:context_end].lower()
        if not _CREDENTIAL_CONTEXT.search(context):
            continue
        entropy = _shannon_entropy(token)
        if entropy >= _ENTROPY_THRESHOLD:
            results.append({
                "text": token,
                "entity_type": "credential",
                "secret_type": "high_entropy_string",
                "severity": "medium",
                "char_offset": m.start(),
                "confidence": min(0.5 + (entropy - _ENTROPY_THRESHOLD) * 0.15, 0.85),
                "extractor": "entropy_scanner",
                "file_id": file_id,
                "detection_method": "entropy",
                "entropy": round(entropy, 2),
            })
    return results


# ── Masking utility ─────────────────────────────────────────


def mask_secret(value: str) -> str:
    """Mask a secret value, showing only first 4 and last 4 chars."""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}{'*' * min(len(value) - 8, 20)}{value[-4:]}"


# ── Main scanner ────────────────────────────────────────────


# Context patterns that indicate a match is inside a file path, URL, hash, or Drive ID
_PATH_CONTEXT_RE = re.compile(
    r"(?:"
    r"[/\\][a-f0-9]{4}[/\\]"        # content-addressable store paths like /ab12/ab12cd...
    r"|sha256[:\s=]"                  # "sha256: abc123..."
    r"|sha1[:\s=]"
    r"|md5[:\s=]"
    r"|[a-f0-9]{64}"                 # full SHA256 hex string
    r"|stored_path"
    r"|parsed_path"
    r"|original_path"
    r"|drivefs\.item-id"             # Google Drive file IDs
    r"|com\.google\."                # Google internal identifiers
    r"|cloudfront\.net/startups"     # CDN image URLs with embedded hashes
    r"|src=\"https?://"              # HTML image/link src attributes
    r"|href=\"https?://"             # HTML link href attributes
    r"|thumb_jpg"                    # Thumbnail URL fragments
    r"|\.cloudfront\.net"            # CloudFront CDN URLs
    r"|startups/i/"                  # AngelList-style CDN paths
    r"|q/0081;00000000"              # macOS xattr binary metadata
    r")",
    re.IGNORECASE,
)


def _is_in_hash_context(text: str, offset: int, value: str) -> bool:
    """Check if a match is inside a file hash/path context (false positive)."""
    context_start = max(0, offset - 100)
    context_end = min(len(text), offset + len(value) + 100)
    context = text[context_start:context_end]
    return bool(_PATH_CONTEXT_RE.search(context))


_BASE58_CHARS = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def _validate_btc_address(addr: str) -> bool:
    """Validate BTC address with Base58Check checksum verification.

    Uses double-SHA256 checksum to eliminate false positives like
    Google Drive file IDs, CDN hashes, and random Base58-like strings.
    """
    if len(addr) < 26 or len(addr) > 35:
        return False
    if addr[0] not in "13LM":
        return False
    # Every character must be valid Base58
    if not all(c in _BASE58_CHARS for c in addr):
        return False
    # Full Base58Check checksum validation
    try:
        import hashlib
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        num = 0
        for c in addr:
            num = num * 58 + alphabet.index(c)
        # Convert to 25 bytes
        combined = num.to_bytes(25, byteorder="big")
        payload = combined[:-4]
        checksum = combined[-4:]
        expected = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return checksum == expected
    except (ValueError, OverflowError):
        return False


def scan_secrets(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Scan text for secrets, credentials, keys, and wallet addresses.

    Returns a list of dicts compatible with regex_extractors.extract_all()
    plus additional keys: secret_type, severity, detection_method.

    Includes post-scan false-positive filtering for:
    - SHA256 hashes in content-addressable file paths
    - Invalid BTC/LTC addresses (wrong length or charset)
    - Hex-only strings that are hash references
    """
    results: list[dict[str, Any]] = []
    seen_offsets: set[int] = set()  # Deduplicate overlapping matches

    for sp in _PATTERNS:
        for m in _safe_finditer(sp.pattern, text):
            offset = m.start()
            if offset in seen_offsets:
                continue

            # Use the first capture group if present, else the full match
            value = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group()

            # ── False positive filters ──────────────────────
            # Skip crypto wallet matches that are in hash/path contexts
            if sp.entity_type == "crypto_wallet":
                if _is_in_hash_context(text, offset, value):
                    continue
                # Validate BTC/LTC addresses with Base58Check checksum
                if sp.secret_type in ("btc_address", "ltc_address") and not _validate_btc_address(value):
                    continue

            # Skip password matches that are just common config defaults
            if sp.secret_type == "plaintext_password":
                if value.lower() in ("true", "false", "null", "none", "yes", "no",
                                      "changeme", "example", "placeholder", "test",
                                      "default", "admin", "root", "password"):
                    continue

            seen_offsets.add(offset)
            results.append({
                "text": value,
                "entity_type": sp.entity_type,
                "secret_type": sp.secret_type,
                "severity": sp.severity,
                "char_offset": offset,
                "confidence": sp.confidence,
                "extractor": "secret_scanner",
                "file_id": file_id,
                "detection_method": "regex",
                "pattern_name": sp.name,
            })

    # Entropy scan as catch-all (heavily filtered — see _entropy_scan docstring)
    entropy_results = _entropy_scan(text, file_id)
    for er in entropy_results:
        if er["char_offset"] not in seen_offsets:
            results.append(er)
            seen_offsets.add(er["char_offset"])

    return results
