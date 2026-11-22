/**
 * UI mirror of the §10 transition table (spec; enforced by the backend in
 * workflow/service.py TRANSITIONS — the API is the referee, this is the
 * map the nav bar renders from).
 *
 * Scope rule: scores.submit / scores.review are honoured at `assigned`
 * scope (the service re-checks teacher assignments); results.* grants are
 * school-scope only — an assigned-scope holder is denied for lack of
 * resource context, so the bar only offers them to school-scope holders.
 *
 * Step-up: lock demands a fresh re-auth; publish demands re-auth WITH a
 * verified TOTP (reauth_mfa claim). A user without MFA enrolled who hits
 * publish gets MFA_REQUIRED from the API and must enrol first — the bar
 * surfaces that as guidance rather than trying to collect a code that can
 * never verify.
 */

export interface TransitionSpec {
  /** URL segment on /api/v1/assessments/{id}/… and the verb shown. */
  action: "submit" | "start-review" | "return" | "approve" | "lock" | "publish" | "correct";
  label: string;
  permission: string;
  /** school = only school-scope holders see the button. */
  scope: "any" | "school";
  reason: "none" | "required";
  stepUp: false | "password" | "password+mfa";
}

const SUBMIT: TransitionSpec = {
  action: "submit",
  label: "Submit for review",
  permission: "scores.submit",
  scope: "any",
  reason: "none",
  stepUp: false,
};

export const STATE_TRANSITIONS: Record<string, TransitionSpec[]> = {
  draft: [SUBMIT],
  returned: [SUBMIT],
  submitted: [
    { action: "start-review", label: "Start review", permission: "scores.review", scope: "any", reason: "none", stepUp: false },
  ],
  under_review: [
    { action: "return", label: "Return to teacher", permission: "scores.review", scope: "any", reason: "required", stepUp: false },
    { action: "approve", label: "Approve", permission: "results.approve", scope: "school", reason: "none", stepUp: false },
  ],
  approved: [
    { action: "lock", label: "Lock results", permission: "results.lock", scope: "school", reason: "none", stepUp: "password" },
  ],
  locked: [
    { action: "publish", label: "Publish", permission: "results.publish", scope: "school", reason: "none", stepUp: "password+mfa" },
  ],
  published: [
    { action: "correct", label: "Correct results", permission: "results.correct", scope: "school", reason: "required", stepUp: false },
  ],
};

/** The typed path for each transition — keeps openapi-fetch's literal unions. */
export const TRANSITION_PATHS = {
  submit: "/api/v1/assessments/{assessment_id}/submit",
  "start-review": "/api/v1/assessments/{assessment_id}/start-review",
  return: "/api/v1/assessments/{assessment_id}/return",
  approve: "/api/v1/assessments/{assessment_id}/approve",
  lock: "/api/v1/assessments/{assessment_id}/lock",
  publish: "/api/v1/assessments/{assessment_id}/publish",
  correct: "/api/v1/assessments/{assessment_id}/correct",
} as const;

export function transitionsFor(state: string): TransitionSpec[] {
  return STATE_TRANSITIONS[state] ?? [];
}
