"""Authorization engine — one function, used everywhere (spec §7.2).

authorize(grants, permission, resource) -> Decision

Steps:
  1. Collect the grants for `permission` from the actor's effective
     permissions.
  2. If no role grants `permission`, deny.
  3. Take the broadest granted scope. `school` allows.
  4. `assigned` — resource must carry assignment keys that resolve into the
     actor's teacher assignments (Phase 2 wires the real resolver; the
     interface is fixed now).
  5. `own` — resource.created_by == actor.id.
  6. Denials on sensitive permissions are audited by the caller.

Enforcement: the `require` FastAPI dependency (dependency.py) is mandatory on
every route; a CI test fails if any route lacks `require` or an explicit
`@public` marker.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.platform.errors import PERMISSION_DENIED, ProblemError

# Permission codes whose denials are always audited (spec §7.2 step 6).
SENSITIVE_PERMISSIONS = frozenset(
    {
        "results.publish",
        "results.correct",
        "roles.manage",
        "permissions.manage",
        "users.delete",
        "audit_logs.view",
    }
)

_SCOPE_BREADTH: dict[str, int] = {"school": 3, "assigned": 2, "own": 1}


@dataclass(frozen=True, slots=True)
class ResourceRef:
    """What a permission is being checked against.

    `assignment_keys` carries the class/section/subject identity the resource
    belongs to — populated by resource loaders; the `assigned` scope matches
    against the actor's teacher_assignments (Phase 2 resolver).
    """

    resource_type: str
    resource_id: Any = None
    created_by: Any = None  # compared to actor id for `own` scope
    assignment_keys: tuple[str, ...] = ()  # e.g. ("class:<id>", "subject:<id>")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    scope: str | None = None
    reason: str = ""


class Actor:
    """The authenticated principal, derived from the JWT — never client input."""

    __slots__ = (
        "user_id",
        "school_id",
        "token_version",
        "session_id",
        "is_super_admin",
    )

    def __init__(
        self,
        *,
        user_id: UUID,
        school_id: UUID,
        token_version: int,
        session_id: UUID,
        is_super_admin: bool = False,
    ) -> None:
        self.user_id = user_id
        self.school_id = school_id
        self.token_version = token_version
        self.session_id = session_id
        self.is_super_admin = is_super_admin


def broadest_scope(scopes: list[str]) -> str | None:
    """The widest scope among the scopes granted for one permission, or None."""
    if not scopes:
        return None
    return max(scopes, key=lambda s: _SCOPE_BREADTH.get(s, 0))


def authorize(
    grants: list[tuple[str, str]],
    permission: str,
    resource: ResourceRef | None = None,
    *,
    actor: Actor | None = None,
) -> Decision:
    """Pure decision function (spec §7.2). `grants` are (code, scope) pairs.

    Raises ProblemError(PERMISSION_DENIED) when the permission is not granted
    or the resource check fails; the caller (dependency) decides about audit
    logging for sensitive permissions.
    """
    relevant = [scope for code, scope in grants if code == permission]
    if not relevant:
        raise ProblemError(PERMISSION_DENIED, f"Missing permission: {permission}", status=403)

    scope = broadest_scope(relevant)
    if scope == "school":
        return Decision(allowed=True, scope=scope)

    if scope == "assigned":
        if resource is None or not resource.assignment_keys:
            return Decision(
                allowed=False,
                scope=scope,
                reason="no resource context for scoped permission",
            )
        # Phase 2 wires the real teacher_assignments resolver; until then the
        # assigned scope requires an explicit resource with assignment keys.
        return Decision(allowed=True, scope=scope)

    # scope == "own"
    if resource is None or actor is None or resource.created_by != actor.user_id:
        return Decision(allowed=False, scope=scope, reason="resource not owned by actor")
    return Decision(allowed=True, scope=scope)


def scope_filter(grants: list[tuple[str, str]], permission: str) -> str:
    """SQL filter helper for list endpoints (spec §7.2).

    Returns the broadest granted scope ('school', 'assigned' or 'own') so list
    queries can add the matching SQL predicate themselves; raises if the
    permission is not granted at all.
    """
    relevant = [scope for code, scope in grants if code == permission]
    if not relevant:
        raise ProblemError(PERMISSION_DENIED, f"Missing permission: {permission}")
    scope = broadest_scope(relevant)
    assert scope is not None  # grants is non-empty here
    return scope
