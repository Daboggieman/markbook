"""Access router — the roles platform (Phase 6).

Phase 1/2 built the machinery (permission catalogue, roles junction tables,
authorize()) but never exposed it: the only way to grant a permission was a
hand-written SQL insert. These endpoints let a super admin do it over HTTP —
create roles, attach permissions, and grant/revoke roles per user — which the
web client's Roles and Users screens consume.

Gating: reading is roles.view / permissions.view; reshaping a role is
roles.manage; granting roles to a *user* is users.edit — except super-admin
roles, which additionally require roles.manage (otherwise a users.edit holder
could mint themselves full power, a privilege-escalation hole).
"""

# ruff: noqa: B008  — Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import schemas
from app.access.dependency import Actor, get_actor_db, load_grants, require
from app.access.models import Role
from app.access.repository import AccessRepository
from app.access.service import authorize
from app.platform.errors import NOT_FOUND, VALIDATION_ERROR, ProblemError

router = APIRouter()


def _with_permissions(
    role: Role, grants: dict[UUID, list[tuple[str, str]]]
) -> schemas.RoleWithPermissions:
    out = schemas.RoleWithPermissions.model_validate(role)
    out.permissions = [
        schemas.EffectivePermission(code=code, scope_type=scope)
        for code, scope in grants.get(role.id, [])
    ]
    return out


async def _validated_codes(repo: AccessRepository, codes: list[str]) -> None:
    """Refuse unknown permission codes with 422 instead of a 500 from the FK."""
    catalogue = {p.code for p in await repo.permissions_all()}
    unknown = [c for c in codes if c not in catalogue]
    if unknown:
        raise ProblemError(
            VALIDATION_ERROR,
            f"Unknown permission code(s): {', '.join(sorted(unknown))}",
            status=422,
        )


async def _school_role(repo: AccessRepository, role_id: UUID, school_id: UUID) -> Role:
    role = await repo.role_by_id(role_id)
    if role is None or role.school_id != school_id:
        raise ProblemError(NOT_FOUND, "Role not found", status=404)
    return role


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@router.get(
    "/roles",
    response_model=list[schemas.RoleWithPermissions],
    dependencies=[Depends(require("roles.view"))],
)
async def list_roles(
    actor: Actor = Depends(require("roles.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> list[schemas.RoleWithPermissions]:
    """Roles for the actor's school, each with its permission grants."""
    repo = AccessRepository(session)
    roles = await repo.roles_for_school(actor.school_id)
    grants = await repo.permissions_for_roles([r.id for r in roles])
    return [_with_permissions(r, grants) for r in roles]


@router.post(
    "/roles",
    response_model=schemas.RoleWithPermissions,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require("roles.manage"))],
)
async def create_role(
    body: schemas.RoleCreate,
    actor: Actor = Depends(require("roles.manage")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.RoleWithPermissions:
    """Create a role, optionally with initial (code, scope) grants."""
    repo = AccessRepository(session)
    await _validated_codes(repo, [code for code, _scope in body.permission_ids])
    role = await repo.create_role(
        school_id=actor.school_id,
        name=body.name,
        description=body.description,
    )
    for code, scope in body.permission_ids:
        await repo.assign_permission_to_role(role.id, code, scope)
    grants = await repo.permissions_for_roles([role.id])
    return _with_permissions(role, grants)


@router.post(
    "/roles/{role_id}/permissions",
    response_model=schemas.RoleWithPermissions,
    dependencies=[Depends(require("roles.manage"))],
)
async def assign_role_permissions(
    role_id: UUID,
    body: schemas.RolePermissionAssign,
    actor: Actor = Depends(require("roles.manage")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.RoleWithPermissions:
    """Attach (or re-scope) permission codes on a role, one scope for all."""
    repo = AccessRepository(session)
    role = await _school_role(repo, role_id, actor.school_id)
    await _validated_codes(repo, body.permission_codes)
    for code in body.permission_codes:
        await repo.assign_permission_to_role(role.id, code, body.scope_type)
    grants = await repo.permissions_for_roles([role.id])
    return _with_permissions(role, grants)


# ---------------------------------------------------------------------------
# Permission catalogue
# ---------------------------------------------------------------------------


@router.get(
    "/permissions",
    response_model=list[schemas.PermissionResponse],
    dependencies=[Depends(require("permissions.view"))],
)
async def list_permissions(
    actor: Actor = Depends(require("permissions.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> list[schemas.PermissionResponse]:
    """The global catalogue seeded at migration time — codes never mutate."""
    repo = AccessRepository(session)
    return [schemas.PermissionResponse.model_validate(p) for p in await repo.permissions_all()]


# ---------------------------------------------------------------------------
# User-role grants
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/roles", dependencies=[Depends(require("users.edit"))])
async def assign_role_to_user(
    user_id: UUID,
    body: schemas.UserRoleAssign,
    actor: Actor = Depends(require("users.edit")),
    session: AsyncSession = Depends(get_actor_db),
) -> dict[str, object]:
    """Grant a role to a user. Super-admin roles additionally need roles.manage."""
    from app.identity.repository import IdentityRepository

    repo = AccessRepository(session)
    role = await _school_role(repo, body.role_id, actor.school_id)
    user = await IdentityRepository(session).get_user_by_id(user_id)
    if user is None or user.school_id != actor.school_id:
        raise ProblemError(NOT_FOUND, "User not found", status=404)
    if role.is_super_admin:
        grants = await load_grants(session, actor.user_id)
        authorize(grants, "roles.manage", None, actor=actor)
    await repo.assign_role_to_user(
        user_id=user_id, role_id=role.id, school_id=actor.school_id, granted_by=actor.user_id
    )
    return {"assigned": True, "user_id": str(user_id), "role_id": str(role.id)}


@router.delete("/users/{user_id}/roles/{role_id}", dependencies=[Depends(require("users.edit"))])
async def revoke_role_from_user(
    user_id: UUID,
    role_id: UUID,
    actor: Actor = Depends(require("users.edit")),
    session: AsyncSession = Depends(get_actor_db),
) -> dict[str, object]:
    """Revoke one role grant."""
    repo = AccessRepository(session)
    removed = await repo.unassign_role_from_user(user_id, role_id)
    return {"removed": removed, "user_id": str(user_id), "role_id": str(role_id)}
