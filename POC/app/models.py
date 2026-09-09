from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class Filters(StrictModel):
    min_parcel_area: float | None = Field(None, ge=0)
    max_units: int | None = Field(None, ge=1)
    max_floors: int | None = Field(None, ge=1)

class Preference(StrictModel):
    field: Literal['parcel_area','units','floors']
    direction: Literal['asc','desc']='desc'

class SearchCenter(StrictModel):
    lat: float = Field(ge=-90,le=90)
    lon: float = Field(ge=-180,le=180)

class SearchRequest(StrictModel):
    center: SearchCenter | None = None
    radius_m: float | None = Field(None,gt=0)
    # Kept only so saved searches from the first POC version remain replayable.
    polygon: dict | None = None
    selection_seed: int | None = Field(None,ge=0)
    filters: Filters=Field(default_factory=Filters)
    preferences: list[Preference]=Field(default_factory=lambda:[Preference(field='parcel_area')],max_length=3)
    @field_validator('preferences')
    @classmethod
    def unique_preferences(cls,value):
        if len({v.field for v in value})!=len(value): raise ValueError('Repeated sort preference')
        return value
    @model_validator(mode='after')
    def one_search_geometry(self):
        circle=self.center is not None or self.radius_m is not None
        if circle and (self.center is None or self.radius_m is None):
            raise ValueError('יש לבחור גם מרכז וגם רדיוס')
        if circle and self.polygon is not None:
            raise ValueError('יש לשלוח מרכז ורדיוס בלבד')
        if not circle and self.polygon is None:
            raise ValueError('יש לבחור נקודת מרכז ורדיוס')
        return self

class ScenarioRequest(StrictModel):
    # No commercial or planning constants are silently supplied.
    sale_area: float=Field(gt=0)
    construction_area: float=Field(gt=0)
    sale_price: float=Field(gt=0)
    build_cost: float=Field(gt=0)
    tenant_rent: float=Field(ge=0)
    rent_months: int=Field(ge=0,le=120)
    consultants: float=Field(ge=0)
    finance: float=Field(ge=0)
    levies_taxes: float=Field(ge=0)
    parking: float=Field(ge=0)
    reserve: float=Field(ge=0)
    other_costs: float=Field(ge=0)
    tax_basis: Literal['all-inclusive','all-exclusive']
    assumptions_note: str=Field(min_length=10,max_length=2000)
