"""
Utility functions for metadata panel.
"""


def format_number(num: int) -> str:
    """Format number with commas."""
    return f"{num:,}" if num else "-"


def format_duration(frame_start: int, frame_end: int, fps: float) -> str:
    """Calculate and format duration from frame range and fps."""
    if not fps or fps <= 0:
        return "-"
    frames = (frame_end or 0) - (frame_start or 0)
    if frames <= 0:
        return "-"
    seconds = frames / fps
    return f"{seconds:.1f} sec"


def format_date(date_str: str) -> str:
    """Format date string for display (truncate to YYYY-MM-DD HH:MM)."""
    if not date_str:
        return "-"
    return date_str[:16]


__all__ = ['format_number', 'format_duration', 'format_date']
