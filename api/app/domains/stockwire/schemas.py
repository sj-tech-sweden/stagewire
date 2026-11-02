from pydantic import BaseModel, Field


class StockwireAdditionItem(BaseModel):
    asset_type: str = Field(..., description="e.g. 'mic', 'di', 'sub-snake'")
    label: str = ""
    quantity: int = 1
    notes: str = ""


class StockwireRequestAdditions(BaseModel):
    items: list[StockwireAdditionItem] = Field(default_factory=list)


class JobProductAvailability(BaseModel):
    """One Stockwire product used by the job and how its stock compares to the need."""

    product_id: str
    product_name: str | None = None
    needed: int = 0
    # available_quantity from the Stockwire endpoint is already the minimum available across
    # the requested date range, so this is the quantity the job can draw on.
    available: int = 0
    total: int = 0
    reserved: int = 0
    short: bool = False


class JobAvailabilityResponse(BaseModel):
    """Availability for every Stockwire-linked product across the job's date range.

    ``configured`` is false when the stockwire-rental integration is not set up, and
    ``missing_dates`` is true when the job has no start/end range to query against.
    """

    configured: bool = True
    missing_dates: bool = False
    start_date: str | None = None
    end_date: str | None = None
    items: list[JobProductAvailability] = Field(default_factory=list)


__all__ = [
    "StockwireAdditionItem",
    "StockwireRequestAdditions",
    "JobProductAvailability",
    "JobAvailabilityResponse",
]
