/**
 * The transition bar under the score sheet: one button per §10 transition
 * available in the current state, filtered by the actor's grants (scope
 * aware — results.* buttons need school scope). Mirror only: the backend
 * re-checks every guard and returns 409/403 as the real referee.
 *
 * Reason-required transitions (return, correct) reveal an inline reason
 * field on click. Step-up transitions (lock, publish) open the re-auth
 * dialog: password first; the TOTP field reveals itself when the API
 * answers MFA_REQUIRED (no profile lookup needed to learn it).
 */
import type { components } from "@markbook/api-client";
import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { reauth, type Profile } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "./ui";
import { unwrap } from "../hooks/useApiQuery";
import { TRANSITION_PATHS, transitionsFor, type TransitionSpec } from "../workflow/transitions";

type Sheet = components["schemas"]["ScoreSheetResponse"];

function holdsGrant(profile: Profile | null, spec: TransitionSpec): boolean {
  if (!profile) return false;
  return profile.effective_permissions.some(
    (p) => p.code === spec.permission && (spec.scope === "any" || p.scope_type === "school"),
  );
}

export function WorkflowBar({
  sheet,
  onChanged,
}: {
  sheet: Sheet;
  onChanged: () => void;
}) {
  const { profile } = useAuth();
  const [active, setActive] = useState<TransitionSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const available = transitionsFor(sheet.workflow_state).filter((t) => holdsGrant(profile, t));
  if (available.length === 0) return null;

  async function fireTransition(spec: TransitionSpec, reason?: string) {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST(TRANSITION_PATHS[spec.action], {
          params: { path: { assessment_id: sheet.assessment_id } },
          body: reason ? { reason } : {},
        }),
      );
      setActive(null);
      onChanged();
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workflow-bar" role="region" aria-label="Workflow actions">
      {error && <ErrorBanner message={error} />}
      {available.map((spec) =>
        active?.action === spec.action ? (
          spec.stepUp ? (
            <StepUpForm
              key={spec.action}
              spec={spec}
              busy={busy}
              onConfirmed={async (reason) => fireTransition(spec, reason)}
              onCancel={() => setActive(null)}
            />
          ) : (
            <ReasonForm
              key={spec.action}
              spec={spec}
              busy={busy}
              onConfirm={async (reason) => fireTransition(spec, reason)}
              onCancel={() => setActive(null)}
            />
          )
        ) : (
          <button
            key={spec.action}
            type="button"
            disabled={busy}
            onClick={() => {
              // reason-none, no step-up → fire on click; anything that
              // needs input goes through the inline form first
              if (spec.reason === "none" && !spec.stepUp) void fireTransition(spec);
              else setActive(spec);
            }}
          >
            {spec.label}
          </button>
        ),
      )}
    </div>
  );
}

/** Inline reason prompt for return/correct — the API rejects an empty one. */
function ReasonForm({
  spec,
  busy,
  onConfirm,
  onCancel,
}: {
  spec: TransitionSpec;
  busy: boolean;
  onConfirm: (reason: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  return (
    <form
      className="inline-form"
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        if (spec.reason === "required" && reason.trim() === "") {
          setLocal("A reason is required.");
          return;
        }
        await onConfirm(reason.trim());
      }}
    >
      <label className="field reason-field">
        <span>Reason</span>
        <input
          name="reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          autoFocus
          aria-label={`${spec.label} reason`}
        />
      </label>
      <button type="submit" disabled={busy}>
        Confirm {spec.label}
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
      {local && <ErrorBanner message={local} />}
    </form>
  );
}

/**
 * Step-up: POST /auth/reauth, then the transition runs with the minted
 * token (authedFetch attaches it). MFA_REQUIRED reveals the TOTP field.
 */
function StepUpForm({
  spec,
  busy,
  onConfirmed,
  onCancel,
}: {
  spec: TransitionSpec;
  busy: boolean;
  onConfirmed: (reason?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [local, setLocal] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLocal(null);
    const result = await reauth(password, needsTotp ? totp : undefined);
    if (!result.ok) {
      if (result.code === "MFA_REQUIRED") {
        setNeedsTotp(true);
        setLocal(
          spec.stepUp === "password+mfa"
            ? "Publishing requires your authenticator code (or MFA enrolment if you have none yet)."
            : "Your account requires an authenticator code.",
        );
      } else {
        setLocal(result.detail ?? "Re-authentication failed");
      }
      return;
    }
    await onConfirmed();
  }

  return (
    <form className="inline-form step-up" onSubmit={submit}>
      <label className="field">
        <span>Password</span>
        <input
          name="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          aria-label="Confirm password"
          required
        />
      </label>
      {needsTotp && (
        <label className="field">
          <span>Authenticator code</span>
          <input
            name="totp"
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={totp}
            onChange={(e) => setTotp(e.target.value)}
            aria-label="Authenticator code"
          />
        </label>
      )}
      <button type="submit" disabled={busy}>
        Confirm
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
      {local && <ErrorBanner message={local} />}
    </form>
  );
}
