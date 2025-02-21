from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_uuid() -> str:
    return str(uuid4())


def generate_datetime_str() -> str:
    return (datetime.utcnow()).replace(tzinfo=timezone.utc).isoformat()


class TestStatus(Enum):
    UNKNOWN = "UNKNOWN"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ABORTED = "ABORTED"
    QUEUED = "QUEUED"


class NotificationsType(Enum):
    EMAIL_RECIPIENTS = "EMAIL_RECIPIENTS"
    MS_TEAMS_CHANNELS = "MS_TEAMS_CHANNELS"
    SLACK_CHANNELS = "SLACK_CHANNELS"


def to_camel_case(key: str) -> str:
    parts = key.split("_")
    for i, part in enumerate(parts[1:]):
        parts[i + 1] = part.capitalize()

    return "".join(parts)


class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel_case
        allow_population_by_field_name = True


class TestRunConfigModel(CamelModel):
    environment: Optional[str] = None
    build: Optional[str] = None


class MilestoneModel(CamelModel):
    id: Optional[int]
    name: Optional[str]


class CiContextModel(CamelModel):
    ci_type: str
    env_variables: Dict[str, str]


class NotificationTargetModel(CamelModel):
    type: str
    value: str


class StartTestRunModel(CamelModel):
    name: str
    framework: str
    started_at: str = Field(default_factory=generate_datetime_str)
    uuid: str = Field(default_factory=generate_uuid)

    config: Optional[TestRunConfigModel] = None
    milestone: Optional[MilestoneModel] = None
    ci_context: Optional[CiContextModel] = None
    notification_targets: Optional[List[NotificationTargetModel]] = None


class LabelModel(CamelModel):
    key: str
    value: str


class CorrelationDataModel(CamelModel):
    name: str


class StartTestModel(CamelModel):
    name: str
    class_name: str
    method_name: str
    uuid: str = Field(default_factory=generate_uuid)
    started_at: str = Field(default_factory=generate_datetime_str)

    correlation_data: Optional[str] = None
    maintainer: Optional[str] = None
    test_case: Optional[str] = None
    labels: Optional[List[LabelModel]] = []


class FinishTestModel(CamelModel):
    result: str
    ended_at: str = Field(default_factory=generate_datetime_str)
    reason: Optional[str] = None


class LogRecordModel(CamelModel):
    test_id: str
    level: str
    timestamp: str
    message: str


class StartTestSessionModel(CamelModel):
    session_id: str
    started_at: str = Field(default_factory=generate_datetime_str)
    desired_capabilities: dict
    capabilities: dict
    test_ids: List[str] = []


class FinishTestSessionModel(CamelModel):
    ended_at: str = Field(default_factory=generate_datetime_str)
    test_ids: List[str] = []


class ArtifactReferenceModel(CamelModel):
    name: str
    value: str


class TestModel(CamelModel):
    name: str
    correlation_data: Optional[CorrelationDataModel]
    status: str
    started_at: datetime
    ended_at: datetime


class RerunDataModel(CamelModel):
    id: str
    run_exists: bool
    rerun_only_failed_tests: bool
    tests: List[TestModel]
