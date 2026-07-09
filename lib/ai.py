"""AI validation seam. Deliberately empty for now.

Good and Bad is a human decision in this build. No Claude API, no OpenAI, no
paid inference. When vision based validation is wanted later, implement the
function below and call it from the import transform step or the review card.
The reviews table and the submissions.flags column already leave room for it.
"""


def suggest_quality(submission: dict) -> dict | None:
    """Return a suggested review for a submission, or None.

    Placeholder for a future model. Would return something like
    {"quality": "good", "confidence": 0.0, "flags": {...}}. Called nowhere for
    now, so this is simply where the seam slots in.
    """
    return None
