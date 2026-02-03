"""
Review System Module

Provides a unified interface for all review operations:
- Review cycles (multi-version review phases)
- Notes (3-state: open, addressed, approved)
- Screenshots and drawovers

Usage:
    from universal_library.services.review import get_review_service

    review = get_review_service()

    # Start a review cycle
    cycle = review.start_cycle(asset_id, 'Base', 'modeling', 'v001', user)

    # Add a note
    note_id = review.add_note(asset_uuid, version_label, text, user, role)

    # Get review status (includes variant awareness)
    status = review.get_status(asset_uuid, version_label, variant_name)
"""

from .review_service import ReviewService, get_review_service

__all__ = [
    'ReviewService',
    'get_review_service',
]
