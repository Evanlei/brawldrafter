"""Typed errors for the recommendation API boundary."""


class RecommendationError(Exception):
    """Base class for recommendation failures."""


class InsufficientCandidatesError(RecommendationError):
    """Fewer than three brawlers remain in the candidate pool."""


class ModelUnavailableError(RecommendationError):
    """Neural scorer required but DraftNet is missing or failed to run."""
