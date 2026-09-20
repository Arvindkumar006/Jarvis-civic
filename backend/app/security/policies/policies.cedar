// Cedar Policies for JARVIS Civic (Application-Level Authorization)
// Least privilege, default-deny policy set.

// POLICY A — Public Tracking
// Allows any authenticated or unauthenticated public user to view public tracking projections
@id("policy_public_tracking")
permit(
    principal,
    action == JarvisCivic::Action::"read_public_tracking",
    resource
)
when {
    resource.is_public == true
};

// POLICY B — Case Creation
// Citizens can create civic grievance cases
@id("policy_citizen_create_case")
permit(
    principal is JarvisCivic::Citizen,
    action == JarvisCivic::Action::"create_case",
    resource
);

// POLICY C — Citizen Ownership
// Citizens can only read, update, add evidence, and accept/reject resolution for cases that they own
@id("policy_citizen_own_case")
permit(
    principal is JarvisCivic::Citizen,
    action in [
        JarvisCivic::Action::"read_own_case",
        JarvisCivic::Action::"update_own_case",
        JarvisCivic::Action::"add_evidence",
        JarvisCivic::Action::"read_evidence",
        JarvisCivic::Action::"accept_resolution",
        JarvisCivic::Action::"reject_resolution"
    ],
    resource
)
when {
    resource.owner == principal
};

// POLICY D — Authority Officer Scope
// Authority officers can read, update status, add resolution notes, attach evidence, and add resolution evidence only within their assigned department
@id("policy_authority_officer_scope")
permit(
    principal is JarvisCivic::AuthorityOfficer,
    action in [
        JarvisCivic::Action::"read_authority_case",
        JarvisCivic::Action::"update_case_status",
        JarvisCivic::Action::"add_resolution_note",
        JarvisCivic::Action::"add_evidence",
        JarvisCivic::Action::"add_resolution_evidence",
        JarvisCivic::Action::"read_evidence",
        JarvisCivic::Action::"request_citizen_confirmation"
    ],
    resource
)
when {
    resource.department == principal.department
};

// POLICY E — Municipal Supervisor Scope
// Supervisors can manage cases, add evidence, add resolution evidence, read evidence, and inspect audit records within their department scope
@id("policy_supervisor_scope")
permit(
    principal is JarvisCivic::MunicipalSupervisor,
    action in [
        JarvisCivic::Action::"read_authority_case",
        JarvisCivic::Action::"update_case_status",
        JarvisCivic::Action::"add_resolution_note",
        JarvisCivic::Action::"add_evidence",
        JarvisCivic::Action::"add_resolution_evidence",
        JarvisCivic::Action::"read_evidence",
        JarvisCivic::Action::"request_citizen_confirmation"
    ],
    resource
)
when {
    resource.department == principal.department
};

@id("policy_supervisor_audit_scope")
permit(
    principal is JarvisCivic::MunicipalSupervisor,
    action == JarvisCivic::Action::"read_audit_log",
    resource
)
when {
    resource.department == principal.department
};

// POLICY F — Administrator Universal Management
// Administrators may perform defined civic operations and audit inspections,
// but CANNOT accept or reject resolutions on behalf of citizens,
// and CANNOT request citizen confirmation (operational role only).
@id("policy_administrator_all")
permit(
    principal is JarvisCivic::Administrator,
    action,
    resource
)
unless {
    action in [
        JarvisCivic::Action::"accept_resolution",
        JarvisCivic::Action::"reject_resolution",
        JarvisCivic::Action::"request_citizen_confirmation"
    ]
};

// POLICY G — Authority Officer Search Scope
// Officers may search dockets only within their assigned department
@id("policy_authority_officer_search")
permit(
    principal is JarvisCivic::AuthorityOfficer,
    action == JarvisCivic::Action::"search_dockets",
    resource
)
when {
    resource.department == principal.department
};

// POLICY H — Municipal Supervisor Search Scope
// Supervisors may search dockets within their assigned department scope
@id("policy_supervisor_search")
permit(
    principal is JarvisCivic::MunicipalSupervisor,
    action == JarvisCivic::Action::"search_dockets",
    resource
)
when {
    resource.department == principal.department
};
