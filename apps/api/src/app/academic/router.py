"""Academic router — structure, enrolment, assignment and promotion endpoints.

HTTP layer only; logic in `academic.service`. Every route declares `require`
(route-coverage guard); tenant-data routes use `get_actor_db` so the RLS
context is set from the JWT.
"""
# ruff: noqa: B008  — Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.academic import schemas
from app.academic.service import AcademicService
from app.access.dependency import get_actor_db, require
from app.access.service import Actor

router = APIRouter(tags=["academic"])


# ---- sessions & terms ------------------------------------------------------


@router.get(
    "/academic-sessions",
    response_model=list[schemas.AcademicSessionResponse],
)
async def list_sessions(
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.AcademicSessionResponse]:
    service = AcademicService(session)
    rows = await service.list_sessions(actor.school_id)
    return [schemas.AcademicSessionResponse.model_validate(r) for r in rows]


@router.post(
    "/academic-sessions",
    response_model=schemas.AcademicSessionResponse,
    status_code=201,
)
async def create_session(
    body: schemas.AcademicSessionCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.AcademicSessionResponse:
    service = AcademicService(session)
    row = await service.create_session(actor.school_id, body)
    await session.commit()
    return schemas.AcademicSessionResponse.model_validate(row)


@router.get("/terms", response_model=list[schemas.TermResponse])
async def list_terms(
    session_id: UUID = Query(),
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.TermResponse]:
    service = AcademicService(session)
    rows = await service.list_terms(actor.school_id, session_id)
    return [schemas.TermResponse.model_validate(r) for r in rows]


@router.post("/terms", response_model=schemas.TermResponse, status_code=201)
async def create_term(
    body: schemas.TermCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.TermResponse:
    service = AcademicService(session)
    row = await service.create_term(actor.school_id, body)
    await session.commit()
    return schemas.TermResponse.model_validate(row)


# ---- levels / classes / sections / subjects -----------------------------------


@router.get(
    "/educational-levels",
    response_model=list[schemas.EducationalLevelResponse],
)
async def list_levels(
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.EducationalLevelResponse]:
    service = AcademicService(session)
    rows = await service.list_levels(actor.school_id)
    return [schemas.EducationalLevelResponse.model_validate(r) for r in rows]


@router.get("/classes", response_model=list[schemas.ClassResponse])
async def list_classes(
    level_id: UUID | None = Query(default=None),
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.ClassResponse]:
    service = AcademicService(session)
    rows = await service.list_classes(actor.school_id, level_id)
    return [schemas.ClassResponse.model_validate(r) for r in rows]


@router.post("/classes", response_model=schemas.ClassResponse, status_code=201)
async def create_class(
    body: schemas.ClassCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.ClassResponse:
    service = AcademicService(session)
    row = await service.create_class(actor.school_id, body)
    await session.commit()
    return schemas.ClassResponse.model_validate(row)


@router.get("/sections", response_model=list[schemas.SectionResponse])
async def list_sections(
    class_id: UUID = Query(),
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.SectionResponse]:
    service = AcademicService(session)
    rows = await service.list_sections(actor.school_id, class_id)
    return [schemas.SectionResponse.model_validate(r) for r in rows]


@router.post("/sections", response_model=schemas.SectionResponse, status_code=201)
async def create_section(
    body: schemas.SectionCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.SectionResponse:
    service = AcademicService(session)
    row = await service.create_section(actor.school_id, body)
    await session.commit()
    return schemas.SectionResponse.model_validate(row)


@router.get("/subjects", response_model=list[schemas.SubjectResponse])
async def list_subjects(
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.SubjectResponse]:
    service = AcademicService(session)
    rows = await service.list_subjects(actor.school_id)
    return [schemas.SubjectResponse.model_validate(r) for r in rows]


@router.post("/subjects", response_model=schemas.SubjectResponse, status_code=201)
async def create_subject(
    body: schemas.SubjectCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.SubjectResponse:
    service = AcademicService(session)
    row = await service.create_subject(actor.school_id, body)
    await session.commit()
    return schemas.SubjectResponse.model_validate(row)


@router.get(
    "/class-subjects",
    response_model=list[schemas.ClassSubjectResponse],
)
async def list_class_subjects(
    class_id: UUID = Query(),
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.ClassSubjectResponse]:
    service = AcademicService(session)
    rows = await service.list_class_subjects(class_id)
    return [schemas.ClassSubjectResponse.model_validate(r) for r in rows]


@router.post(
    "/class-subjects",
    response_model=schemas.ClassSubjectResponse,
    status_code=201,
)
async def create_class_subject(
    body: schemas.ClassSubjectCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.ClassSubjectResponse:
    service = AcademicService(session)
    row = await service.create_class_subject(actor.school_id, body)
    await session.commit()
    return schemas.ClassSubjectResponse.model_validate(row)


# ---- enrolments / teacher assignments ------------------------------------------


@router.post("/enrolments", response_model=schemas.EnrolmentResponse, status_code=201)
async def create_enrolment(
    body: schemas.EnrolmentCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.EnrolmentResponse:
    """Enrol a student: creates the enrolment and one subject_enrolment per
    class subject (spec §6.3). One live enrolment per student per session —
    a second returns 409."""
    service = AcademicService(session)
    row = await service.enrol_student(actor.school_id, body)
    await session.commit()
    return schemas.EnrolmentResponse.model_validate(row)


@router.get(
    "/teacher-assignments",
    response_model=list[schemas.TeacherAssignmentResponse],
)
async def list_teacher_assignments(
    session_id: UUID = Query(),
    teacher_user_id: UUID | None = Query(default=None),
    actor: Actor = Depends(require("academic.view")),
    session=Depends(get_actor_db),
) -> list[schemas.TeacherAssignmentResponse]:
    """Defaults to the caller's own assignments (teachers read theirs;
    academic.manage holders pass another user)."""
    service = AcademicService(session)
    target = teacher_user_id or actor.user_id
    rows = await service.list_teacher_assignments(actor.school_id, target, session_id)
    return [schemas.TeacherAssignmentResponse.model_validate(r) for r in rows]


@router.post(
    "/teacher-assignments",
    response_model=schemas.TeacherAssignmentResponse,
    status_code=201,
)
async def create_teacher_assignment(
    body: schemas.TeacherAssignmentCreate,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.TeacherAssignmentResponse:
    service = AcademicService(session)
    row = await service.create_teacher_assignment(actor.school_id, body)
    await session.commit()
    return schemas.TeacherAssignmentResponse.model_validate(row)


# ---- promotions --------------------------------------------------------------------


@router.post("/promotions/run", response_model=schemas.PromotionRunResponse)
async def run_promotion(
    body: schemas.PromotionRunRequest,
    actor: Actor = Depends(require("academic.manage")),
    session=Depends(get_actor_db),
) -> schemas.PromotionRunResponse:
    """End-of-session promotion run (spec §6.3). Per-student decisions; each
    runs in a savepoint so one bad row doesn't sink the batch."""
    service = AcademicService(session)
    result = await service.run_promotion(actor.school_id, body, actor.user_id)
    await session.commit()
    return result
