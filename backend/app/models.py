from typing import Literal, Annotated
from datetime import date
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

Money = Annotated[float, Field(ge=0, le=100_000_000, allow_inf_nan=False)]
Label = Annotated[str, Field(min_length=1, max_length=100)]
Importance = Literal['MUST PAY', 'FLEXIBLE', 'CAN WAIT']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class LinkedAccount(Model):
    source: Literal['plaid'] | None = None
    plaidAccountId: str | None = None
    plaidItemId: str | None = None
    institution: str = 'Manual snapshot'
    type: str | None = None
    subtype: str | None = None
    current: float | None = Field(default=None, allow_inf_nan=False)
    available: float | None = Field(default=None, allow_inf_nan=False)
    creditLimit: float | None = Field(default=None, allow_inf_nan=False)
    currency: str | None = None


class Account(LinkedAccount):
    id: Label
    name: Label
    institution: str = 'Manual snapshot'
    balance: float = Field(ge=-100_000_000, le=100_000_000, allow_inf_nan=False)
    last4: str | None = Field(default=None, pattern=r'^\d{4}$')


class Card(LinkedAccount):
    id: Label
    name: Label
    last4: str = Field(pattern=r'^(\d{4})?$')
    balance: Money
    limit: float = Field(ge=0, le=100_000_000, allow_inf_nan=False)
    status: Literal['active', 'locked'] = 'active'
    preferred: bool = False
    rewards: dict[str, Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]]

    @field_validator('rewards')
    @classmethod
    def default_reward(cls, v):
        if 'default' not in v or len(v) > 100: raise ValueError('Include a default reward rate; maximum 100 categories.')
        return v


class Goal(Model):
    id: Label
    name: Label
    saved: Money
    target: Money
    protected: Money


class Debt(Model):
    name: Label
    balance: Money
    monthlyPayment: Money = 0
    status: str = ''


class Upcoming(Model):
    id: Label
    merchant: Label
    category: Label
    amount: Money
    date: date
    essential: bool = True


class Recurring(Model):
    id: Label
    merchant: Label
    category: Label
    amount: Money
    nextDate: date
    essential: bool = False
    inferred: bool = False
    flag: str | None = None


class Settings(Model):
    revision: int
    accounts: list[Account] = Field(max_length=100)
    cards: list[Card] = Field(max_length=100)
    goals: list[Goal] = Field(max_length=100)
    debts: list[Debt] = Field(max_length=100)
    upcoming: list[Upcoming] = Field(max_length=200)
    recurring: list[Recurring] = Field(max_length=200)
    buffer: Money
    guardrail: Literal['balanced', 'strict']
    balancesConfirmed: bool
    categoryImportance: dict[str, Importance]

    @model_validator(mode='after')
    def unique_ids(self):
        for name in ('accounts', 'cards', 'goals', 'upcoming', 'recurring'):
            rows = getattr(self, name)
            if len({r.id for r in rows}) != len(rows): raise ValueError(f'Duplicate IDs in {name}')
        if sum(c.preferred for c in self.cards) > 1: raise ValueError('Choose at most one preferred card.')
        return self


class Authorization(Model):
    cardToken: str = Field(min_length=1, max_length=100)
    merchant: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    category: Label
    importance: Importance | None = None
    requestId: str | None = Field(default=None, min_length=8, max_length=100)

    @field_validator('amount')
    @classmethod
    def cents(cls, value):
        if abs(value*100-round(value*100)) > .000001: raise ValueError('Use at most two decimal places.')
        return value


class CoachRequest(Model):
    question: str = Field(min_length=1, max_length=2000)


class RandomizeRequest(Model):
    revision: int = Field(ge=1)


class CategoryUpdate(Model):
    revision: int
    oldName: Label | None = None
    name: Label
    importance: Importance
    limit: Money | None = None


class LithicSimulation(Model):
    merchant: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    category: Label
    requestId: str = Field(min_length=8, max_length=100)

    _cents = field_validator('amount')(Authorization.cents.__func__)


class PlaidLinkRequest(Model):
    itemId: str | None = Field(default=None, max_length=200)


class PlaidExchangeRequest(Model):
    public_token: str = Field(min_length=10, max_length=1000)


class PlaidSyncRequest(Model):
    background: bool = False
