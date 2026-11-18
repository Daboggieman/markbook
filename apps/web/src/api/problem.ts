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
  if (isProblem(error)) {
    if (error.errors?.length) {
      return error.errors.map((e) => `${e.loc.join(".")}: ${e.msg}`).join("; ");
    }
    return error.detail || error.title;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
