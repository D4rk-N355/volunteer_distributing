from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lng: float


class Metadata(BaseModel):
    incident_id: str
    priority_weighting: Literal['balanced', 'speed', 'expertise']


class WorkType(BaseModel):
    type_id: str
    required_skills: List[str]


class Volunteer(BaseModel):
    id: str
    skills: List[str]
    location: Location
    availability: bool
    age: Optional[int] = None
    line_user_id: Optional[str] = None
    special_skills: Optional[List[str]] = None


class Task(BaseModel):
    id: str
    type_id: str
    location: Location
    urgency: int = Field(..., ge=1, le=5)


class DispatchRequest(BaseModel):
    metadata: Metadata
    work_types: List[WorkType]
    volunteers: List[Volunteer]
    tasks: List[Task]


class DispatchSetupRequest(BaseModel):
    metadata: Metadata
    work_types: List[WorkType]
    tasks: List[Task]


class ScoreBreakdown(BaseModel):
    skill_score: float
    distance_score: float
    urgency_score: float
    final_score: float


class Assignment(BaseModel):
    task_id: str
    assigned_volunteers: List[str]
    eta_minutes: int
    confidence: float
    score_breakdown: ScoreBreakdown
    reasoning_summary: str


class DispatchResponse(BaseModel):
    status: str
    dispatch_id: str
    incident_id: str
    mode: Literal['algorithm_only', 'algorithm_with_ai_anomaly_check']
    assignments: List[Assignment]
    unassigned_tasks: List[str]
    warnings: List[str]


class LineVolunteerRegistration(BaseModel):
    line_user_id: str
    display_name: str
    group_id: Optional[str] = None
    skills: Optional[List[str]] = None
    address: Optional[str] = None
    location: Optional[Location] = None
    availability: bool = True


class LineRegisterResponse(BaseModel):
    status: str
    line_user_id: str
    group_id: str
    message: str
