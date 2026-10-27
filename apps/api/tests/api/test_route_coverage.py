"""Route-coverage guard (Phase 1 deliverable, spec §7.2 / 02-api-conventions).

Fails the build if any route is reachable without `require(...)` or an
explicit `@public` marker: an unauthenticated route without `@public` is a
defect, and an authenticated one without `require` is an authorization hole.
"""

from fastapi.routing import APIRoute

from app.access.dependency import _PUBLIC_ATTR
from app.main import create_app

# Framework endpoints FastAPI registers itself — not part of the app's
# permission-checked API surface (OpenAPI document and docs UIs).
_FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _route_is_guarded(route: APIRoute) -> bool:
    """The route is public, or a dependency from access.dependency guards it."""
    if getattr(route.endpoint, _PUBLIC_ATTR, False):
        return True
    # require() returns a closure defined in app.access.dependency; both
    # parameter-level Depends(...) and router-level dependencies=[...] end up
    # in dependant.dependencies.
    return any(
        getattr(dep.call, "__module__", "") == "app.access.dependency"
        for dep in route.dependant.dependencies
    )


def _classify() -> tuple[list[APIRoute], list[APIRoute]]:
    """(guarded, unguarded) APIRoutes on the app, framework paths excluded."""
    app = create_app()
    guarded: list[APIRoute] = []
    unguarded: list[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in _FRAMEWORK_PATHS:
            continue
        (guarded if _route_is_guarded(route) else unguarded).append(route)
    return guarded, unguarded


def _labels(routes: list[APIRoute]) -> list[str]:
    return [f"{'/'.join(sorted(r.methods or set()))} {r.path}" for r in routes]


def test_every_route_declares_require_or_public() -> None:
    _, unguarded = _classify()
    assert unguarded == [], _labels(unguarded)


def test_known_public_routes_are_marked() -> None:
    """login, refresh, health are the documented public routes (02-api-conventions)."""
    _, unguarded = _classify()
    offenders = [r.path for r in unguarded if r.path.endswith(("/login", "/refresh", "/health"))]
    assert not offenders, f"public routes must carry @public, found unmarked: {offenders}"


def test_at_least_one_route_is_guarded() -> None:
    """If the app ever ships without guards at all, the guard must not pass vacuously."""
    guarded, _ = _classify()
    assert guarded, "no guarded routes found — the guard itself is broken"
