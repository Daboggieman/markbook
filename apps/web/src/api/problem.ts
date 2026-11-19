/**
 * Typed RFC 7807 Problem Details from every API error.
 * Every page uses this to surface backend validation or state errors.
 */
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  instance?: string;
  request_id?: string;
  errors?: { loc: string[]; msg: string; type: string }[];
}

/** True when fetch-style `error` is a Problem (not network/cors). */
export function isProblem(error: unknown): error is Problem {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    "code" in error
  );
}

/** The human-readable message for any error from openapi-fetch. */
export function problemMessage(error: unknown): string {
  // FastAPI's default validation handler (422) is NOT our Problem shape —
  // it puts an array of {loc, msg, type} under `detail`. Handle it first.
  const detail = (error as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => `${(e.loc ?? []).map(String).join(".")}: ${e.msg}`)
      .join("; ");
  }
  if (isProblem(error)) {
    if (error.errors?.length) {
      return error.errors.map((e) => `${e.loc.join(".")}: ${e.msg}`).join("; ");
    }
    return error.detail || error.title;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
