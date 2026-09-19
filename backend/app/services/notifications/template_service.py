"""Email Template Service for JARVIS Civic.

Phase 8.4: Server-rendered deterministic notification templates.
Strictly adheres to product terminology:
- "AI-generated Civic Action Docket"
- "Recommended Department"
- Explicit disclaimers regarding prototype status and non-governmental representation.
"""

from html import escape
from typing import Optional, Tuple
from app.models.security import CivicCaseRecord

DISCLAIMER_TEXT = (
    "DISCLAIMER: JARVIS Civic is an AI-assisted civic decision-support prototype. "
    "This communication concerns an AI-generated civic grievance record and does NOT "
    "represent official government petition registration, municipal department acceptance, "
    "or legally binding resolution."
)


class EmailTemplateService:
    """Renders deterministic plain text and semantic HTML notification emails."""

    def render_case_created_citizen(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        tracking_url: str,
    ) -> Tuple[str, str, str]:
        """Render case confirmation email for the citizen reporting the issue."""
        subject = f"[JARVIS Civic] Civic Action Docket Created: {case.case_id}"

        text_body = f"""Dear {recipient_name},

Your civic issue report has been recorded as an AI-generated Civic Action Docket.

DOCKET DETAILS:
- Docket ID: {case.case_id}
- Summary: {case.description}
- Location: {case.location}
- Recommended Department: {case.department}
- Initial Lifecycle Stage: {case.status.value}

PUBLIC TRACKING:
You can track the public lifecycle of this docket at:
{tracking_url}

{DISCLAIMER_TEXT}

Thank you,
JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #3b82f6; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #1e3a8a; margin: 0; font-size: 20px;">JARVIS Civic — Action Docket Recorded</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">AI-Assisted Decision Support Intake</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>Your civic issue has been intake-processed into an <strong>AI-generated Civic Action Docket</strong>.</p>

    <div style="background: #f1f5f9; border-left: 4px solid #3b82f6; padding: 16px; margin: 20px 0; border-radius: 4px;">
      <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; color: #64748b; width: 160px;"><strong>Docket ID:</strong></td><td><code>{escape(case.case_id)}</code></td></tr>
        <tr><td style="padding: 4px 0; color: #64748b;"><strong>Recommended Dept:</strong></td><td>{escape(case.department)}</td></tr>
        <tr><td style="padding: 4px 0; color: #64748b;"><strong>Location:</strong></td><td>{escape(case.location)}</td></tr>
        <tr><td style="padding: 4px 0; color: #64748b;"><strong>Current Stage:</strong></td><td><span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 9999px; font-weight: 600; font-size: 12px;">{escape(case.status.value)}</span></td></tr>
      </table>
      <p style="margin: 12px 0 0 0; font-size: 13px; color: #334155;"><strong>Issue Summary:</strong> {escape(case.description)}</p>
    </div>

    <p style="margin: 24px 0 16px 0;">You may follow docket progress via the safe public tracking projection:</p>
    <a href="{escape(tracking_url)}" style="display: inline-block; background: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 500;">View Public Tracking</a>

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_case_created_authority(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        officer_assigned: bool,
    ) -> Tuple[str, str, str]:
        """Render notification email for the responsible department authority."""
        subject = f"[JARVIS Civic — Triage] New Docket in Jurisdiction: {case.case_id} ({case.department})"

        assignment_line = (
            f"Assigned for departmental triage to: {recipient_name}"
            if officer_assigned
            else f"Routed to {case.department} departmental inbox for triage review."
        )

        text_body = f"""Attention: {recipient_name},

A new civic grievance has been routed to your department jurisdiction for decision support review.

DOCKET SUMMARY:
- Docket ID: {case.case_id}
- Recommended Department: {case.department}
- Location: {case.location}
- Lifecycle Stage: {case.status.value}
- Description: {case.description}
- Routing State: {assignment_line}

Please review this docket in your Authority Workspace console.

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #0284c7; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #0369a1; margin: 0; font-size: 20px;">Department Triage Alert</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Jurisdiction: {escape(case.department)}</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>A new citizen grievance has been routed for departmental triage evaluation:</p>

    <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 16px; margin: 20px 0; border-radius: 4px;">
      <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>Docket ID:</strong> <code>{escape(case.case_id)}</code></p>
      <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>Location:</strong> {escape(case.location)}</p>
      <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>Lifecycle Stage:</strong> {escape(case.status.value)}</p>
      <p style="margin: 0 0 8px 0; font-size: 14px; color: #0369a1;"><strong>Routing Status:</strong> {escape(assignment_line)}</p>
      <p style="margin: 8px 0 0 0; font-size: 13px; color: #334155;"><strong>Issue Statement:</strong> {escape(case.description)}</p>
    </div>

    <p style="font-size: 13px; color: #64748b;">Please open the Authority Workspace to inspect evidence, attach notes, or update stage progression.</p>

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_stage_changed(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        previous_stage: str,
        new_stage: str,
        note: Optional[str] = None,
        tracking_url: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Render notification when case status transitions forward in the canonical lifecycle."""
        subject = f"[JARVIS Civic] Status Update on Docket {case.case_id}: {new_stage}"

        note_section = f"\nAuthority Transition Note: {note}" if note else ""

        text_body = f"""Dear {recipient_name},

The lifecycle stage of civic docket {case.case_id} has advanced.

STATUS TRANSITION:
- Docket ID: {case.case_id}
- Previous Stage: {previous_stage}
- Updated Stage: {new_stage}{note_section}

{f"Track online: {tracking_url}" if tracking_url else ""}

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #10b981; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #065f46; margin: 0; font-size: 20px;">Docket Status Progressed</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Docket {escape(case.case_id)}</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>A lifecycle update was recorded for civic docket <strong>{escape(case.case_id)}</strong>:</p>

    <div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 16px; margin: 20px 0; border-radius: 4px;">
      <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>Previous Stage:</strong> {escape(previous_stage)}</p>
      <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>New Stage:</strong> <span style="background: #a7f3d0; color: #065f46; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">{escape(new_stage)}</span></p>
      {f'<p style="margin: 8px 0 0 0; font-size: 13px; color: #047857;"><strong>Transition Note:</strong> {escape(note)}</p>' if note else ''}
    </div>

    {f'<p><a href="{escape(tracking_url)}" style="display: inline-block; background: #059669; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 13px;">View Public Status</a></p>' if tracking_url else ''}

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_evidence_available(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        filename: str,
        content_type: str,
    ) -> Tuple[str, str, str]:
        """Render notification when new validated evidence has been attached to a case."""
        subject = f"[JARVIS Civic] New Evidence Attached: {case.case_id}"

        text_body = f"""Dear {recipient_name},

New evidence artifact has been attached to civic docket {case.case_id}:

EVIDENCE DETAILS:
- Docket ID: {case.case_id}
- Filename: {filename}
- Content Type: {content_type}

This artifact is stored securely in backend case storage.

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <h3 style="color: #4338ca; margin-top: 0;">Evidence Artifact Attached</h3>
    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>A new verified evidence file was added to docket <strong>{escape(case.case_id)}</strong>:</p>
    <ul>
      <li><strong>Filename:</strong> {escape(filename)}</li>
      <li><strong>Content Type:</strong> {escape(content_type)}</li>
    </ul>
    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0 12px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_resolution_ready(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        note: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Render resolution readiness notice (infrastructure only, no closure trigger)."""
        subject = f"[JARVIS Civic] Proposed Resolution Ready: {case.case_id}"

        text_body = f"""Dear {recipient_name},

A proposed resolution has been recorded for civic docket {case.case_id}.

DOCKET: {case.case_id}
{f"Resolution Note: {note}" if note else ""}

Please review the proposed resolution in JARVIS Civic.

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <h3 style="color: #0f766e; margin-top: 0;">Proposed Resolution Ready</h3>
    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>Proposed resolution details are now available for docket <strong>{escape(case.case_id)}</strong>:</p>
    {f'<p style="background: #f0fdfa; border-left: 4px solid #0f766e; padding: 12px;">{escape(note)}</p>' if note else ''}
    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0 12px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_resolution_confirmed_citizen(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        feedback: Optional[str] = None,
        tracking_url: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Render resolution confirmation receipt for the citizen."""
        subject = f"[JARVIS Civic] Resolution Confirmed: {case.case_id} (Resolved & Closed)"

        feedback_sec = f"\nYour Feedback: {feedback}" if feedback else ""

        text_body = f"""Dear {recipient_name},

You have successfully reviewed and confirmed the resolution of civic docket {case.case_id}.
The docket has now transitioned to RESOLVED and is closed in the civic decision-support system.{feedback_sec}

{f"View final docket: {tracking_url}" if tracking_url else ""}

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #10b981; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #065f46; margin: 0; font-size: 20px;">Resolution Confirmed — Docket Closed</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Docket {escape(case.case_id)}</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>You have confirmed the resolution of civic docket <strong>{escape(case.case_id)}</strong>. The case has successfully transitioned to <strong>RESOLVED</strong>.</p>

    {f'<div style="background: #f0fdf4; border-left: 4px solid #10b981; padding: 12px; margin: 16px 0;"><p style="margin: 0; font-size: 13px; color: #166534;"><strong>Your Feedback:</strong> {escape(feedback)}</p></div>' if feedback else ''}

    {f'<p><a href="{escape(tracking_url)}" style="display: inline-block; background: #059669; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 13px;">View Final Docket</a></p>' if tracking_url else ''}

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_resolution_confirmed_authority(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        feedback: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Render resolution confirmation alert for the department authority."""
        subject = f"[JARVIS Civic — Closed] Citizen Confirmed Resolution: {case.case_id}"

        feedback_sec = f"\nCitizen Feedback: {feedback}" if feedback else ""

        text_body = f"""Attention: {recipient_name},

The citizen owner of civic docket {case.case_id} ({case.department}) has reviewed and confirmed the resolution.
The case lifecycle has reached final state: RESOLVED.{feedback_sec}

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #059669; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #065f46; margin: 0; font-size: 20px;">Citizen Confirmed Resolution</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Department: {escape(case.department)}</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>Citizen confirmation received for docket <strong>{escape(case.case_id)}</strong>. The docket is formally <strong>RESOLVED</strong>.</p>

    {f'<p style="background: #f0fdf4; border-left: 4px solid #059669; padding: 12px; font-size: 13px; color: #065f46;"><strong>Citizen Feedback:</strong> {escape(feedback)}</p>' if feedback else ''}

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_resolution_rejected_authority(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        reason: str,
    ) -> Tuple[str, str, str]:
        """Render notification to authority when citizen rejects proposed resolution."""
        subject = f"[JARVIS Civic — Action Required] Citizen Rejected Resolution: {case.case_id}"

        text_body = f"""Attention: {recipient_name},

The citizen owner of civic docket {case.case_id} has REJECTED the proposed resolution.
The docket remains in UNDER_REVIEW and requires corrective action or additional inspection.

CITIZEN REJECTION REASON:
{reason}

Please inspect the docket in your Authority Workspace to perform corrective actions and submit updated resolution evidence.

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <div style="border-bottom: 2px solid #dc2626; padding-bottom: 12px; margin-bottom: 24px;">
      <h2 style="color: #991b1b; margin: 0; font-size: 20px;">Resolution Rejected by Citizen — Rework Required</h2>
      <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Docket {escape(case.case_id)} // {escape(case.department)}</p>
    </div>

    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>The citizen has reviewed the submitted resolution for docket <strong>{escape(case.case_id)}</strong> and indicated that the defect remains unresolved.</p>

    <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; margin: 16px 0; border-radius: 4px;">
      <p style="margin: 0 0 4px 0; font-size: 12px; color: #991b1b; font-weight: 700;">CITIZEN'S STATED REASON:</p>
      <p style="margin: 0; font-size: 14px; color: #7f1d1d;">{escape(reason)}</p>
    </div>

    <p style="font-size: 13px; color: #475569;">The case remains in <strong>UNDER_REVIEW</strong>. Please perform corrective work and submit revised resolution evidence.</p>

    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 32px 0 16px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body

    def render_resolution_rejected_citizen(
        self,
        case: CivicCaseRecord,
        recipient_name: str,
        reason: str,
    ) -> Tuple[str, str, str]:
        """Render notification acknowledging citizen's resolution rejection."""
        subject = f"[JARVIS Civic] Resolution Rejection Logged: {case.case_id}"

        text_body = f"""Dear {recipient_name},

Your feedback has been recorded. You have rejected the proposed resolution for civic docket {case.case_id}.
The case remains in UNDER_REVIEW and the responsible municipal department has been notified to carry out further rework.

REASON RECORDED:
{reason}

{DISCLAIMER_TEXT}

JARVIS Civic Decision Support
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 32px;">
    <h3 style="color: #b91c1c; margin-top: 0;">Resolution Rejection Recorded</h3>
    <p>Dear <strong>{escape(recipient_name)}</strong>,</p>
    <p>Your objection to the resolution of docket <strong>{escape(case.case_id)}</strong> has been logged. The case remains in <strong>UNDER_REVIEW</strong>.</p>
    <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 12px 0;">
      <p style="margin: 0; font-size: 13px; color: #7f1d1d;"><strong>Reason:</strong> {escape(reason)}</p>
    </div>
    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0 12px 0;">
    <p style="font-size: 11px; color: #94a3b8; line-height: 1.5; margin: 0;">
      <strong>DISCLAIMER:</strong> {escape(DISCLAIMER_TEXT)}
    </p>
  </div>
</body>
</html>
"""
        return subject, text_body, html_body


# Global singleton instance
email_template_service = EmailTemplateService()
