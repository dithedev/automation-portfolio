"""Runtime validation of domain enum values."""

from enum import StrEnum

from app.texts.validation import ENUM_MEMBER_REQUIRED


def ensure_enum_member[EnumT: StrEnum](
    value: object,
    enum_type: type[EnumT],
    field_name: str,
) -> EnumT:
    """Require an instance of the expected enum without coercing strings.

    Integration adapters must convert external strings before constructing
    domain entities.

    Raises:
        TypeError: If the value is not a member of the expected enum.
    """
    if not isinstance(value, enum_type):
        raise TypeError(
            ENUM_MEMBER_REQUIRED.format(
                field_name=field_name,
                enum_name=enum_type.__name__,
            )
        )

    return value
