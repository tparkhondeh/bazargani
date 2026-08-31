from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from trade_agent.domain.workflow import ResearchRunStatus


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str


class OpportunityCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=300)
    quantity: int = Field(gt=0)
    target_market: str = Field(min_length=1, max_length=200)


class OpportunityView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_name: str
    quantity: int
    target_market: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    opportunity_id: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunTransition(BaseModel):
    target_status: ResearchRunStatus
    expected_version: int = Field(gt=0)
