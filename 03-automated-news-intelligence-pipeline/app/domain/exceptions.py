from app.texts.domain import INVALID_STATE_TRANSITION


class DomainError(Exception):
    """Base exception for domain errors."""


class InvalidStateTransitionError(DomainError):
    """Raised when an entity cannot transition to the requested status."""

    def __init__(
        self,
        entity: str,
        current_status: str,
        target_status: str,
    ) -> None:
        """Initialize the exception with the rejected transition."""
        self.entity = entity
        self.current_status = current_status
        self.target_status = target_status

        super().__init__(
            INVALID_STATE_TRANSITION.format(
                entity=entity,
                current_status=current_status,
                target_status=target_status,
            )
        )
