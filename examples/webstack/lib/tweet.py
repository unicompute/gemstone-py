"""
Port of webstack/lib/magtag/tweet.rb
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time as time_module


def twitterize_date(ts: float, reference: float = None) -> str:
    """Convert a unix timestamp to a human-friendly relative string."""
    reference = reference or time_module.time()
    seconds_ago = int(reference - ts)
    if seconds_ago < 60:
        return f"{seconds_ago} seconds ago"
    elif seconds_ago < 3600:
        return f"{seconds_ago // 60} minutes ago"
    elif seconds_ago < 86400:
        return f"{seconds_ago // 3600} hours ago"
    else:
        return f"{seconds_ago // 86400} days ago"
