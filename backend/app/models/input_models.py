"""
Input schema for a renewal case.

Every field that feeds a calculation or a decision is REQUIRED and has no default.
A case file with a missing or wrongly-typed field is rejected with a clear error
instead of being filled in with an invented value.

Fields typed Optional[...] = None are descriptive only (shown in the brief when
present, never used in a calculation); None means "not provided", not a guess.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class _Strict(BaseModel):
    # Allow extra keys so richer source files still load, but never invent missing ones.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class VendorInfo(_Strict):
    name: str = Field(min_length=1)
    service_type: str = Field(min_length=1)
    account_manager: Optional[str] = None
    account_manager_email: Optional[str] = None
    vendor_tier: Optional[str] = None


class MSAInfo(_Strict):
    contract_id: str = Field(min_length=1)
    signed_date: date
    current_term_start: date
    current_term_end: date
    notice_period_days: StrictInt = Field(ge=0)
    auto_renewal: StrictBool
    termination_for_convenience: StrictBool
    governing_law: Optional[str] = None
    payment_terms_days: Optional[StrictInt] = None
    price_increase_cap_pct: Optional[float] = None

    @model_validator(mode="after")
    def _term_order(self):
        if self.current_term_end <= self.current_term_start:
            raise ValueError("current_term_end must be after current_term_start")
        return self


class CurrentPricing(_Strict):
    annual_contract_value: float = Field(gt=0)
    total_seats: StrictInt = Field(gt=0)
    unit_price_per_seat: float = Field(gt=0)
    billing_frequency: Optional[str] = None
    modules_included: Optional[List[str]] = None
    currency: Optional[str] = None


class VendorProposal(_Strict):
    received_date: date
    proposed_annual_value: float = Field(gt=0)
    proposed_seats: StrictInt = Field(gt=0)
    proposed_unit_price: float = Field(gt=0)
    proposed_term_months: StrictInt = Field(gt=0)
    proposed_modules: Optional[List[str]] = None
    price_increase_justification: Optional[str] = None
    proposal_expiry_date: Optional[date] = None


class IncidentDetail(_Strict):
    date: date
    duration_hours: float = Field(ge=0)
    impacted_users: StrictInt = Field(ge=0)


class SLAInfo(_Strict):
    contracted_uptime_pct: float = Field(ge=0, le=100)
    contracted_support_response_hours: float = Field(ge=0)
    contracted_resolution_hours: float = Field(ge=0)
    actual_uptime_pct: float = Field(ge=0, le=100)
    actual_support_sla_achievement_pct: float = Field(ge=0, le=100)
    critical_incidents_count: StrictInt = Field(ge=0)
    critical_incidents_detail: List[IncidentDetail]
    service_credits_claimed_usd: float = Field(ge=0)
    service_credits_available_usd: float = Field(ge=0)


class AddendumItem(_Strict):
    addendum_id: str = Field(min_length=1)
    signed_date: date
    description: str
    status: str = Field(pattern="^(active|expired)$")
    expiry: Optional[date] = None


class DepartmentUsage(_Strict):
    name: str
    provisioned: StrictInt = Field(ge=0)
    active: StrictInt = Field(ge=0)


class UsageInfo(_Strict):
    total_provisioned_seats: StrictInt = Field(ge=0)
    active_seats_last_90_days: StrictInt = Field(ge=0)
    inactive_seats: StrictInt = Field(ge=0)
    departments: List[DepartmentUsage]
    feature_adoption: Dict[str, float]


class RoadmapMilestone(_Strict):
    feature: str
    promised_date: date
    delivered: StrictBool
    actual_date: Optional[date] = None


class RoadmapInfo(_Strict):
    promised_milestones: List[RoadmapMilestone]


class EmailLog(_Strict):
    date: date
    from_: str = Field(alias="from")
    subject: str
    summary: str


class RenewalHistoryItem(_Strict):
    renewal_cycle: str
    original_acv: float = Field(ge=0)
    renewed_acv: float = Field(ge=0)
    increase_pct: float
    seats: StrictInt = Field(ge=0)
    term_months: StrictInt = Field(gt=0)
    outcome: str
    negotiated_savings_usd: float


class InternalAssessment(_Strict):
    strategic_importance: str = Field(min_length=1)
    replacement_difficulty: str = Field(min_length=1)
    known_alternatives: List[str]
    migration_estimate_months: StrictInt = Field(ge=0)
    budget_owner: str = Field(min_length=1)
    approved_budget_acv: float = Field(ge=0)
    internal_champion: Optional[str] = None


class RenewalInputData(_Strict):
    case_id: str = Field(min_length=1)
    vendor: VendorInfo
    msa: MSAInfo
    current_pricing: CurrentPricing
    vendor_proposal: VendorProposal
    sla: SLAInfo
    addendum: List[AddendumItem]
    usage: UsageInfo
    roadmap: RoadmapInfo
    emails: List[EmailLog]
    renewal_history: List[RenewalHistoryItem]
    internal_assessment: InternalAssessment


class ProcessRequest(BaseModel):
    case_id: int  # Contracts.ContractId
    as_of: Optional[date] = None


class UploadCaseRequest(BaseModel):
    filename: str
    data: Dict[str, Any]
    uploaded_by: Optional[str] = Field(default=None, max_length=100)


class PdfExportRequest(BaseModel):
    result_id: int
    exported_by: str = Field(min_length=1, max_length=100)
