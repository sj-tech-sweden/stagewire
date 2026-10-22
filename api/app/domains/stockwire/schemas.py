from pydantic import BaseModel, Field


class StockwireAdditionItem(BaseModel):
    asset_type: str = Field(..., description="e.g. 'mic', 'di', 'sub-snake'")
    label: str = ""
    quantity: int = 1
    notes: str = ""


class StockwireRequestAdditions(BaseModel):
    items: list[StockwireAdditionItem] = Field(default_factory=list)


__all__ = ["StockwireAdditionItem", "StockwireRequestAdditions"]
