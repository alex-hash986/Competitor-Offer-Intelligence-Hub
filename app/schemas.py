from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Mode = Literal["raw_html", "json_snapshot", "manual_text", "live_url"]
Severity = Literal["high", "medium", "low"]
CaseID = Literal["b2b_agency", "edtech"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class CompetitorCreate(BaseModel):
    name: Name
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253)]
    segment: Literal["direct", "indirect", "leader"]
    is_own_brand: bool = False
    positioning_note: str = ""
    target_audience: str = ""


class PageCreate(BaseModel):
    competitor_id: int = Field(gt=0)
    page_type: Literal["main", "pricing", "promo", "lead_magnet"]
    url: HttpUrl
    title: str = ""
    is_active: bool = True


class BattlecardWrite(BaseModel):
    competitor_strength: str
    our_counter_offer: str
    sales_objection_script: str


class SnapshotInput(BaseModel):
    mode: Mode
    content: str | dict | None = None

    @model_validator(mode="after")
    def validate_content(self):
        if self.mode != "live_url" and self.content is None:
            raise ValueError("content is required in offline modes")
        if isinstance(self.content, dict) and self.mode != "json_snapshot":
            raise ValueError("Object content is supported only in json_snapshot mode")
        return self


class CaptureInput(SnapshotInput):
    page_id: int = Field(gt=0)


class StructuredSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str | None = None
    h1_text: str = ""
    subheadline: str = ""
    prices: list[Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]] = Field(default_factory=list)
    currency: Literal["RUB", "USD", "EUR"] = "RUB"
    cta_buttons: list[str] = Field(default_factory=list)
    trust_signals: list[str] = Field(default_factory=list)
    lead_magnets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_variant(self):
        if self.html is not None and self.model_fields_set != {"html"}:
            raise ValueError("html and structured fields cannot be combined")
        if self.html is None and not (self.model_fields_set - {"html"}):
            raise ValueError("Provide html or structured fields")
        return self


class DemoReset(BaseModel):
    case_id: CaseID
