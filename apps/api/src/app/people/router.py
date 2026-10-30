"""People router — student and guardian endpoints (Phase 2).

HTTP layer only; logic in `people.service`. Every route declares `require`
or `require_with_scope` (route-coverage guard). Routes reading tenant data
use `get_actor_db`, which sets the RLS tenant context from the JWT — plain
`get_db` leaves it unset and RLS then hides every row.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.access.dependency import get_actor_db, require, require_with_scope
from app.access.service import Actor
from app.people import schemas
from app.people.service import PeopleService

router = APIRouter(tags=["people"])


# NOTE: literal paths (check-duplicates) precede /{student_id} so FastAPI
# does not try to parse "check-duplicates" as a UUID.


@router.get("/students", response_model=list[schemas.StudentResponse])
async def list_students(
    auth: tuple[Actor, str] = Depends(require_with_scope("students.view")),
    session=Depends(get_actor_db),
    session_id: UUID | None = Query(default=None),
    class_id: UUID | None = Query(default=None),
    status: str | None = Query(
        default=None, pattern="^(active|graduated|withdrawn|archived)$"
    ),
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[schemas.StudentResponse]:
    """Roster, name-ordered. 'assigned'-scope callers see only their own
    classes (teacher assignments, spec §7.2); requires session_id then."""
    actor, scope = auth
    service = PeopleService(session)
    students = await service.list_students(
        scope=scope,
        school_id=actor.school_id,
        teacher_user_id=actor.user_id,
        session_id=session_id,
        class_id=class_id,
        status=status,
        q=q,
        limit=limit,
    )
    return [schemas.StudentResponse.model_validate(s) for s in students]


@router.post(
    "/students/check-duplicates",
    response_model=schemas.DuplicateCheckResponse,
)
async def check_duplicates(
    body: schemas.DuplicateCheckRequest,
    actor: Actor = Depends(require("students.check-duplicates")),
    session=Depends(get_actor_db),
) -> schemas.DuplicateCheckResponse:
    """Trigram similarity search (spec §6.2). Looser threshold than the
    creation block — this is the eyeball tool."""
    service = PeopleService(session)
    return await service.check_duplicates(actor.school_id, body)


@router.get("/students/{student_id}", response_model=schemas.StudentResponse)
async def get_student(
    student_id: UUID,
    actor: Actor = Depends(require("students.view")),
    session=Depends(get_actor_db),
) -> schemas.StudentResponse:
    service = PeopleService(session)
    student = await service.get_student(actor.school_id, student_id)
    return schemas.StudentResponse.model_validate(student)


@router.post(
    "/students",
    response_model=schemas.StudentResponse,
    status_code=201,
)
async def create_student(
    body: schemas.StudentCreate,
    actor: Actor = Depends(require("students.create")),
    session=Depends(get_actor_db),
) -> schemas.StudentResponse:
    """Create a student. Very similar names return 409 POSSIBLE_DUPLICATE
    with the candidates; re-send with allow_duplicate=true to proceed."""
    service = PeopleService(session)
    student = await service.create_student(actor.school_id, body)
    await session.commit()
    return schemas.StudentResponse.model_validate(student)


@router.patch("/students/{student_id}", response_model=schemas.StudentResponse)
async def update_student(
    student_id: UUID,
    body: schemas.StudentUpdate,
    actor: Actor = Depends(require("students.edit")),
    session=Depends(get_actor_db),
) -> schemas.StudentResponse:
    service = PeopleService(session)
    student = await service.update_student(actor.school_id, student_id, body)
    await session.commit()
    return schemas.StudentResponse.model_validate(student)


@router.post("/students/{student_id}/archive", response_model=schemas.StudentResponse)
async def archive_student(
    student_id: UUID,
    body: schemas.StudentArchive,
    actor: Actor = Depends(require("students.archive")),
    session=Depends(get_actor_db),
) -> schemas.StudentResponse:
    """Archive, never delete (spec §6). Enrolments and results keep their
    context — the row is stamped, not removed."""
    service = PeopleService(session)
    student = await service.archive_student(actor.school_id, student_id, body.version)
    await session.commit()
    return schemas.StudentResponse.model_validate(student)


@router.get(
    "/students/{student_id}/guardians",
    response_model=list[schemas.GuardianResponse],
)
async def list_student_guardians(
    student_id: UUID,
    actor: Actor = Depends(require("students.view")),
    session=Depends(get_actor_db),
) -> list[schemas.GuardianResponse]:
    service = PeopleService(session)
    await service.get_student(actor.school_id, student_id)  # 404 when absent
    guardians = await service.list_guardians(student_id)
    return [schemas.GuardianResponse.model_validate(g) for g in guardians]


@router.post("/guardians", response_model=schemas.GuardianResponse, status_code=201)
async def create_guardian(
    body: schemas.GuardianCreate,
    actor: Actor = Depends(require("students.create")),
    session=Depends(get_actor_db),
) -> schemas.GuardianResponse:
    service = PeopleService(session)
    guardian = await service.create_guardian(actor.school_id, body)
    await session.commit()
    return schemas.GuardianResponse.model_validate(guardian)


@router.post("/students/{student_id}/guardians")
async def link_guardian(
    student_id: UUID,
    body: schemas.GuardianLinkRequest,
    actor: Actor = Depends(require("students.edit")),
    session=Depends(get_actor_db),
) -> dict[str, str]:
    service = PeopleService(session)
    await service.link_guardian(actor.school_id, student_id, body)
    await session.commit()
    return {"status": "linked"}
