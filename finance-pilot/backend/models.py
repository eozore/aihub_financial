"""Pydantic models for request/response validation."""
from pydantic import BaseModel
from typing import Optional, Literal


class TenantContext(BaseModel):
    tenant_id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None


class TransactionUpdate(BaseModel):
    """Model for updating an existing transaction — all fields optional."""
    date: Optional[str] = None
    amount: Optional[float] = None
    merchant_clean: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    owner: Optional[str] = None
    type: Optional[str] = None


class TransactionCreate(BaseModel):
    """Model for creating a new transaction."""
    date: str
    amount: float
    merchant_clean: str
    category: str
    subcategory: Optional[str] = None
    owner: str
    type: str


class PlanUpdate(BaseModel):
    plan_type: Literal["free", "paid"]


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceUpdate(BaseModel):
    name: str


class WorkspaceInviteCreate(BaseModel):
    invitee_email: str
    invite_mode: Literal["shared", "isolated"] = "shared"
    target_workspace_name: Optional[str] = None


class NetWorthRowUpdate(BaseModel):
    salary: Optional[float] = None
    other_income: Optional[float] = None
    income_total: Optional[float] = None
    expense_fixed: Optional[float] = None
    expense_variable: Optional[float] = None
    expense_total: Optional[float] = None
    cash_end_balance: Optional[float] = None
    net_worth_total: Optional[float] = None
    debt_ratio: Optional[float] = None
    notes: Optional[str] = None


class UserProfileUpdate(BaseModel):
    """Model for updating user profile fields."""
    display_name: Optional[str] = None
    short_name: Optional[str] = None
    photo_url: Optional[str] = None
    birth_date: Optional[str] = None  # YYYY-MM-DD
    cpf: Optional[str] = None
    address: Optional[str] = None
