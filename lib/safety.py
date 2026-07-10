"""Small safety helpers shared across the app.

These guard the two places untrusted spreadsheet content reaches a user: the
browser (HTML and link rendering) and a re-exported CSV (spreadsheet formula
injection). Photo URLs are rendered by the browser, not fetched by the server,
so there is no server side request forgery, but we still validate the scheme so
a stray value cannot become a javascript link.
"""

import html
import re

_HTTP_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_CSV_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def is_safe_url(value) -> bool:
    """True only for a plain http or https URL. Blanks, javascript: and data:
    are rejected so we never render them as an image source or a link."""
    return bool(value) and isinstance(value, str) and _HTTP_URL.match(value.strip()) is not None


def escape_html(value) -> str:
    """Escape a value before it goes into markup rendered with
    unsafe_allow_html."""
    return html.escape(str(value if value is not None else ""))


_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~])")


def escape_md(value) -> str:
    """Escape untrusted text so st.markdown cannot interpret it as HTML,
    a link or emphasis. Used for filenames and display names in the feed."""
    return _MD_SPECIAL.sub(r"\\\1", str(value if value is not None else ""))


def sanitize_csv_value(value):
    """Neutralise spreadsheet formula injection for CSV export.

    Only strings that begin with a formula trigger get a leading apostrophe, and
    only when they are not a plain number, so a genuine negative latitude like
    -8.45 stays a number and a malicious "=cmd|..." becomes inert text.
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] in _CSV_TRIGGERS:
        try:
            float(value)
        except ValueError:
            return "'" + value
    return value
