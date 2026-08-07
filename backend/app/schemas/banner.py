from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.banner import BannerColour

# Long enough for a real notice, short enough that it stays a banner
# rather than becoming a page.
MAX_BANNER_LENGTH = 500


class BannerUpdate(BaseModel):
    message: str
    colour: BannerColour
    is_active: bool

    @field_validator("message")
    @classmethod
    def message_must_fit(cls, value: str) -> str:
        if len(value) > MAX_BANNER_LENGTH:
            raise ValueError(f"message must be {MAX_BANNER_LENGTH} characters or fewer")
        return value

    @model_validator(mode="after")
    def active_banner_needs_text(self):
        # An active banner with no text renders as an empty coloured bar
        # with a close button and nothing to explain it. A model validator
        # rather than a field one because it needs both fields together.
        if self.is_active and not self.message.strip():
            raise ValueError("an active banner needs a message")
        return self


class BannerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    colour: BannerColour
    is_active: bool
    # The frontend stores this against a dismissal, so changing the banner
    # un-dismisses it for everyone (see components/Banner.jsx).
    updated_at: datetime
