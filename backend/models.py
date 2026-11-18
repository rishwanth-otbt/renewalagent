from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Input Models ---

class VendorInfo(BaseModel):
    name: str
    service_type: str
    account_manager: Optional[str] = None
    account_manager_email: Optional[str] = None
    vendor_tier: Optional[str] = None

class MSAInfo(BaseModel):
    contract_id: str
    signed_date: str
    current_term_start: str
    current_term_end: str
    notice_period_days: int = 60
    auto_renewal: bool = True
    governing_law: Optional[str] = None
    payment_terms_days: Optional[int] = 30
    termination_for_convenience: bool = False
    price_increase_cap_pct: Optional[float] = None

class CurrentPricing(BaseModel):
    annual_contract_value: float
    total_seats: int
    unit_price_per_seat: float
    billing_frequency: Optional[str] = "annual"
    modules_included: List[str] = []
    currency: Optional[str] = "USD"

class VendorProposal(BaseModel):
    received_date: str
    proposed_annual_value: float
    proposed_seats: int
    proposed_unit_price: float
    proposed_term_months: int = 36
    proposed_modules: List[str] = []
    price_increase_justification: Optional[str] = None
    proposal_expiry_date: Optional[str] = None

class IncidentDetail(BaseModel):
    date: str
    duration_hours: float
    impacted_users: int

class SLAInfo(BaseModel):
    contracted_uptime_pct: float
    contracted_support_response_hours: float
    contracted_resolution_hours: float
    actual_uptime_pct: float
    actual_support_sla_achievement_pct: float
    critical_incidents_count: int
    critical_incidents_detail: List[IncidentDetail] = []
    service_credits_claimed_usd: float = 0.0
    service_credits_available_usd: float = 0.0

class AddendumItem(BaseModel):
    addendum_id: str
    signed_date: str
    description: str
    expiry: Optional[str] = None
    status: str

class DepartmentUsage(BaseModel):
    name: str
    provisioned: int
    active: int

class UsageInfo(BaseModel):
    total_provisioned_seats: int
    active_seats_last_90_days: int
    inactive_seats: int
    departments: List[DepartmentUsage] = []
    feature_adoption: Dict[str, float] = {}

class RoadmapMilestone(BaseModel):
    feature: str
    promised_date: str
    delivered: bool
    actual_date: Optional[str] = None

class RoadmapInfo(BaseModel):
    promised_milestones: List[RoadmapMilestone] = []

class EmailLog(BaseModel):
    date: str
    from_: Optional[str] = Field(None, alias="from")
    subject: str
    summary: str

class RenewalHistoryItem(BaseModel):
    renewal_cycle: str
    original_acv: float
    renewed_acv: float
    increase_pct: float
    seats: int
    term_months: int
    outcome: str
    negotiated_savings_usd: float = 0.0

class InternalAssessment(BaseModel):
    strategic_importance: str
    replacement_difficulty: str
    known_alternatives: List[str] = []
    migration_estimate_months: int = 6
    internal_champion: Optional[str] = None
    budget_owner: Optional[str] = None
    approved_budget_acv: float

class RenewalInputData(BaseModel):
    case_id: str
    vendor: VendorInfo
    msa: MSAInfo
    current_pricing: CurrentPricing
    vendor_proposal: VendorProposal
    sla: SLAInfo
    addendum: List[AddendumItem] = []
    usage: UsageInfo
    roadmap: RoadmapInfo
    emails: List[EmailLog] = []
    renewal_history: List[RenewalHistoryItem] = []
    internal_assessment: InternalAssessment

class ProcessRequest(BaseModel):
    case_id: str

class UploadCaseRequest(BaseModel):
    filename: str
    data: Dict[str, Any]
