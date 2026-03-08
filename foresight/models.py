"""foresight domain model. dataclasses for the parsed DSL."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Duration:
    value: int
    unit: str

@dataclass
class Qualification:
    name: str
    category: str = ""
    regulatory_body: Optional[str] = None
    issuing_body: Optional[str] = None
    validity: Optional[Duration] = None
    recency: Optional[Duration] = None
    renewal: Optional[str] = None
    prerequisites: list[str] = field(default_factory=list)
    min_experience: Optional[Duration] = None
    description: Optional[str] = None

@dataclass
class Training:
    name: str
    renews: str
    duration: Optional[Duration] = None
    type: Optional[str] = None
    location: Optional[str] = None
    capacity: Optional[int] = None
    cost: Optional[float] = None

@dataclass
class HoldsRecord:
    qualification: str
    issued: date | None
    last_used: date | None = None

@dataclass
class ScheduledTraining:
    training: str
    scheduled: date | None

@dataclass
class Staff:
    name: str
    role: str
    base: Optional[str] = None
    career_start: Optional[date] = None
    day_rate: Optional[float] = None
    holds: list[HoldsRecord] = field(default_factory=list)
    trainings: list[ScheduledTraining] = field(default_factory=list)

@dataclass
class TimeWindow:
    start: date
    end: date

@dataclass
class Requirements:
    qualifications: list[str] = field(default_factory=list)
    role: Optional[str] = None
    min_staff: Optional[int] = None

@dataclass
class Task:
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    aircraft: Optional[str] = None
    location: Optional[str] = None
    window: Optional[TimeWindow] = None
    requires: Optional[Requirements] = None
    prefer: Optional[str] = None

@dataclass
class ForesightModel:
    qualifications: dict[str, Qualification] = field(default_factory=dict)
    trainings: dict[str, Training] = field(default_factory=dict)
    staff: dict[str, Staff] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)