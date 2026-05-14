"""Тесты для API схем и зависимостей."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas.task import TaskCreateRequest, TaskResponse
from api.schemas.doctor import DoctorResponse, DoctorAvailabilityRequest
from api.schemas.config import AlgorithmConfigRequest
from data.models import TaskState, UrgencyClass


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_valid():
    """TaskCreateRequest валидирует корректные данные."""
    request = TaskCreateRequest(
        external_id=str(uuid4()),
        modality="ECG_REST",
        urgency_class="план",
        complexity=1.5,
    )
    assert request.external_id is not None
    assert request.modality == "ECG_REST"
    assert request.urgency_class == "план"
    assert request.complexity == 1.5


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_missing_field():
    """TaskCreateRequest выбрасывает ошибку при пропуске обязательного поля."""
    with pytest.raises(ValidationError):
        TaskCreateRequest(
            external_id=str(uuid4()),
            modality="ECG_REST",
            # urgency_class отсутствует
            complexity=1.0,
        )


@pytest.mark.unit
@pytest.mark.api


def test_task_create_request_accepts_small_complexity():
    """TaskCreateRequest принимает маленькие значения complexity."""
    request = TaskCreateRequest(
        external_id=str(uuid4()),
        modality="ECG_REST",
        urgency_class="план",
        complexity=0.05,
    )
    assert request.complexity == 0.05


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_accepts_large_complexity():
    """TaskCreateRequest принимает большие значения complexity."""
    request = TaskCreateRequest(
        external_id=str(uuid4()),
        modality="ECG_REST",
        urgency_class="план",
        complexity=20.0,
    )
    assert request.complexity == 20.0
@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_all_urgencies():
    """TaskCreateRequest принимает все допустимые urgency_class значения."""
    urgencies = ["план", "CITO", "срочно"]
    for urgency in urgencies:
        request = TaskCreateRequest(
            external_id=str(uuid4()),
            modality="ECG_REST",
            urgency_class=urgency,
            complexity=1.0,
        )
        assert request.urgency_class == urgency


@pytest.mark.unit
@pytest.mark.api
def test_task_response_contains_required_fields():
    """TaskResponse имеет все необходимые поля."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    response = TaskResponse(
        id=uuid4(),
        external_id="test-123",
        modality="ECG_REST",
        urgency_class="план",
        complexity=1.0,
        arrived_at=now,
        deadline_target=now,
        deadline_max=now,
        state=TaskState.QUEUED.value,
        assigned_to=None,
        started_at=None,
        done_at=None,
        escalated_at=None,
        estimated_tat_h=None,
    )
    assert response.id is not None
    assert response.state == TaskState.QUEUED.value


@pytest.mark.unit
@pytest.mark.api
def test_doctor_availability_request_valid():
    """DoctorAvailabilityRequest валидирует корректные данные."""
    request = DoctorAvailabilityRequest(is_available=True)
    assert request.is_available is True


@pytest.mark.unit
@pytest.mark.api
def test_doctor_availability_request_false():
    """DoctorAvailabilityRequest может быть False."""
    request = DoctorAvailabilityRequest(is_available=False)
    assert request.is_available is False


@pytest.mark.unit
@pytest.mark.api
def test_doctor_response_structure():
    """DoctorResponse имеет корректную структуру."""
    response = DoctorResponse(
        id=uuid4(),
        specializations=["ECG_STRESS"],
        productivity_rate=0.95,
        is_available=True,
        current_load=0.5,
        normalized_load=None,
    )
    assert response.specializations == ["ECG_STRESS"]
    assert response.productivity_rate == 0.95


@pytest.mark.unit
@pytest.mark.api
def test_algorithm_config_request_valid():
    """AlgorithmConfigRequest валидирует корректные данные."""
    request = AlgorithmConfigRequest(type="EDF")
    assert request.type == "EDF"


@pytest.mark.unit
@pytest.mark.api
def test_algorithm_config_request_with_params():
    """AlgorithmConfigRequest может содержать параметры алгоритма."""
    request = AlgorithmConfigRequest(
        type="HYBRID",
        epsilon=0.5,
        beta=0.8,
    )
    assert request.type == "HYBRID"
    assert request.epsilon == 0.5
    assert request.beta == 0.8


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_boundary_complexity():
    """TaskCreateRequest принимает граничные значения complexity."""
    # Минимальное допустимое
    req_min = TaskCreateRequest(
        external_id=str(uuid4()),
        modality="ECG_REST",
        urgency_class="план",
        complexity=0.1,
    )
    assert req_min.complexity == 0.1

    # Максимальное допустимое
    req_max = TaskCreateRequest(
        external_id=str(uuid4()),
        modality="ECG_REST",
        urgency_class="план",
        complexity=10.0,
    )
    assert req_max.complexity == 10.0


@pytest.mark.unit
@pytest.mark.api
def test_task_state_enum_values():
    """TaskState enum содержит все ожидаемые значения."""
    expected_states = [
        TaskState.QUEUED,
        TaskState.ASSIGNED,
        TaskState.ESCALATED,
        TaskState.DONE,
    ]
    assert len(expected_states) >= 4


@pytest.mark.unit
@pytest.mark.api
def test_urgency_class_enum_values():
    """UrgencyClass enum содержит все ожидаемые значения."""
    urgencies = [uc.value for uc in UrgencyClass]
    assert "план" in urgencies
    assert "CITO" in urgencies


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_external_id_required():
    """TaskCreateRequest требует external_id."""
    with pytest.raises(ValidationError):
        TaskCreateRequest(
            modality="ECG_REST",
            urgency_class="план",
            complexity=1.0,
        )


@pytest.mark.unit
@pytest.mark.api
def test_task_create_request_modality_required():
    """TaskCreateRequest требует modality."""
    with pytest.raises(ValidationError):
        TaskCreateRequest(
            external_id=str(uuid4()),
            urgency_class="план",
            complexity=1.0,
        )
