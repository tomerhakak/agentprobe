"""Redaction engine for stripping sensitive data from recordings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class _Pattern:
    """A named redaction pattern."""

    label: str
    regex: re.Pattern[str]


# ---------------------------------------------------------------------------
# Built-in patterns
# ---------------------------------------------------------------------------

_BUILTIN_PATTERNS: list[_Pattern] = [
    _Pattern(
        label="API_KEY",
        regex=re.compile(
            r"""(?:sk-[A-Za-z0-9_\-]{20,})"""       # OpenAI-style
            r"""|(?:key-[A-Za-z0-9_\-]{20,})"""      # generic key-xxx
            r"""|(?:api[_\-]?key\s*[:=]\s*["']?)[A-Za-z0-9_\-]{16,}""",
            re.IGNORECASE,
        ),
    ),
    _Pattern(
        label="AWS_ACCESS_KEY",
        regex=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    _Pattern(
        label="AWS_SECRET_KEY",
        regex=re.compile(r"(?i)(?:aws_secret_access_key\s*[:=]\s*[\"']?)[A-Za-z0-9/+=]{40}"),
    ),
    _Pattern(
        label="PRIVATE_KEY",
        regex=re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    _Pattern(
        label="EMAIL",
        regex=re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),
    ),
    _Pattern(
        label="SSN",
        regex=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    _Pattern(
        label="CREDIT_CARD",
        regex=re.compile(r"\b(?:\d[ \-]*?){13,19}\b"),
    ),
    _Pattern(
        label="PHONE",
        regex=re.compile(
            r"(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"
        ),
    ),
    _Pattern(
        label="IP_ADDRESS",
        regex=re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class RedactionEngine:
    """Redacts sensitive information from text and dictionaries.

    Parameters
    ----------
    custom_patterns:
        Optional list of ``{"label": "NAME", "pattern": "regex_string"}``
        dicts that will be compiled and applied *in addition to* the built-in
        patterns.
    enabled:
        Master switch.  When ``False``, ``redact`` and ``redact_dict`` are
        no-ops that return their input unchanged.
    """

    custom_patterns: list[dict[str, str]] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self) -> None:
        self._patterns: list[_Pattern] = list(_BUILTIN_PATTERNS)
        for entry in self.custom_patterns:
            label = entry.get("label", "CUSTOM")
            pattern_str = entry.get("pattern", "")
            if pattern_str:
                self._patterns.append(
                    _Pattern(label=label, regex=re.compile(pattern_str))
                )

    # -- Public API ---------------------------------------------------------

    def redact(self, text: str) -> str:
        """Return *text* with all sensitive values replaced by ``[REDACTED_<LABEL>]``."""
        if not self.enabled:
            return text
        for pat in self._patterns:
            text = pat.regex.sub(f"[REDACTED_{pat.label}]", text)
        return text

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact all string values in a (possibly nested) dict."""
        if not self.enabled:
            return data
        return self._walk(data)  # type: ignore[return-value]

    # -- Internal -----------------------------------------------------------

    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {k: self._walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._walk(item) for item in obj]
        if isinstance(obj, tuple):
            return tuple(self._walk(item) for item in obj)
        return obj
