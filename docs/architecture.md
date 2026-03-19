# Nephew CRM Architecture

## Suggested architecture

- `core`: project settings, global URL routing, and environment-level wiring.
- `common`: shared abstractions such as timestamps, public identifiers, encryption helpers, phone normalization, matching helpers, Bootstrap form helpers, middleware, and generic mixins.
- `accounts`: custom user model, registration, login, logout, and account-focused services.
- `organizations`: tenant domain, memberships, invite codes, onboarding, organization switching, and permission-sensitive services.
- `dashboard`: authenticated application pages that depend on the active organization context.
- `admin_panel`: global administrative surface restricted by Django auth groups, with access-audit visibility outside tenant scope.
- `dispatch_flow`: unified dispatch workspace that reuses Bot Conversa and Gmail dispatch components when those apps are installed, keeping the page focused on channel choice, audience, and send cadence.
- `companies`: tenant-scoped CRM companies.
- `people`: tenant-scoped CRM persons and contact identity.
- `integrations`: app catalog, tenant installations, encrypted credentials, and credential access audit.
- `apollo_integration`: Apollo API key wiring, remote company search, person search, synchronous person enrichment, webhook-backed phone reveal jobs, usage snapshots, bulk import, and optional company sync handoff to HubSpot.
- `bot_conversa`: Bot Conversa contact linking, tag cache, flow cache, dispatching, and sync logs.
- `hubspot_integration`: HubSpot company/contact/business synchronization, deal-stage pipeline cache, local business-person associations, and async business selection helpers.
- `gmail_integration`: Gmail credential management, templates, and email dispatches.

## Folder structure

```text
NephewCRM/
|-- core/
|-- common/
|-- accounts/
|-- organizations/
|-- dashboard/
|-- dispatch_flow/
|-- companies/
|-- people/
|-- integrations/
|-- apollo_integration/
|-- bot_conversa/
|-- hubspot_integration/
|-- gmail_integration/
|-- templates/
|   `-- partials/
|-- static/
|   |-- css/
|   `-- js/
`-- docs/
```

## Domain model

### `accounts.User`

- Uses Django auth with a custom user model from day one.
- Authenticates with `email`.
- Stores `full_name` for UI and auditing.
- Stores `email` encrypted at rest.
- Uses `email_lookup` as a deterministic HMAC-based lookup index for login and uniqueness checks.

### `organizations.Organization`

- Shared-schema tenant model.
- Stores `name`, `slug`, `segment`, `team_size`, `is_active`, `created_by`.
- Includes `public_id`, `created_at`, and `updated_at`.

### `organizations.OrganizationMembership`

- Join table between `User` and `Organization`.
- Stores `role`, `is_active`, `invited_by`, `created_at`, `updated_at`.
- Enforces one membership per user per organization.
- Enforces a single active `owner` per organization.

### `organizations.OrganizationInvite`

- Tenant-scoped invite code model.
- Stores `code`, `target_role`, `status`, `created_by`, `used_by`, `expires_at`, `redeemed_at`.
- Uses unique codes with `ADM XXXXXXXX` and `USR XXXXXXXX` patterns.
- Includes `public_id`, `created_at`, and `updated_at`.

### `admin_panel.AdminAccessLog`

- Global audit table for authenticated session access.
- Stores `user`, `logged_in_by`, `logged_out_by`, `session_key`, `ip_address`, `user_agent`, `logged_in_at`, and `logged_out_at`.
- Supports administrative visibility of who entered and left the system and from which IP.

### `companies.Company`

- Tenant-scoped CRM company table.
- Stores `organization`, `name`, `website`, `phone`, `normalized_phone`, `email`, `segment`, `employee_count`, `hubspot_company_id`, `apollo_company_id`, `is_active`, and audit ownership fields.
- A company belongs to only one organization and is not shared globally between tenants.

### `people.Person`

- Tenant-scoped CRM person table.
- Stores `organization`, optional `company`, `phone`, `normalized_phone`, `email`, `email_lookup`, `first_name`, `last_name`, `apollo_person_id`, `hubspot_contact_id`, `bot_conversa_id`, active flag, and audit ownership fields.
- Uses normalized phone and deterministic email lookup for uniqueness and matching.
- Acts as the shared identity hub for Apollo, HubSpot, and Bot Conversa, so the integrations stay operationally independent while still converging into one tenant-scoped person when matching succeeds.

### `hubspot_integration.HubSpotPipelineCache`

- Tenant-scoped cache of remote HubSpot pipelines for object type `deals`.
- Stores `hubspot_pipeline_id`, `name`, `object_type`, `raw_payload`, and `last_synced_at`.
- Keeps stage metadata in `raw_payload` so the UI can offer valid HubSpot deal columns without hardcoding labels.

### `hubspot_integration.HubSpotDeal`

- Tenant-scoped local mirror of HubSpot deals, exposed in the UI as `Negócios`.
- Stores `organization`, `installation`, `company`, `pipeline`, `persons`, `hubspot_deal_id`, `name`, `amount`, `stage_id`, `sync_status`, `raw_payload`, and audit ownership fields.
- Supports associating one company and multiple local people to the same HubSpot business record.

## Roles and permissions

- System role source:
  Django `auth_group`, using global groups such as `Admin` and `User`.
- `owner`
  Highest organization role. Can manage invites, members, integrations, and organization-level actions.
- `admin`
  Can manage invites and tenant-scoped operational actions inside the active organization.
- `user`
  Can access tenant-safe workspace modules but cannot execute manager-only actions.
- `Admin` group
  Can access the global `Painel Admin`, including the IP access audit screens.
- `User` group
  Default global system group without access to `Painel Admin`.

## Multi-tenancy decisions

- Strategy: shared schema with row-level tenant isolation.
- Active tenant source: `active_organization_id` in session.
- Request resolution: middleware loads `request.active_organization` and `request.active_membership`.
- Global administrative authorization is independent from tenant membership and is validated by Django auth group membership.
- Authenticated requests also pass through a global access-audit middleware that guarantees the current session IP is persisted, even when the session was already active before the request.
- Safe switching: only via POST to `organizations/switch/` after validating membership.
- Fallback behavior: when a user has memberships but no active organization in session, the middleware selects the first valid membership.
- No access: when a user has no memberships, dashboard renders an empty state instead of tenant data.

## Repositories

- `accounts.repositories.UserRepository`
  Encapsulates account creation and email lookup.
- `organizations.repositories.OrganizationRepository`
  Encapsulates organization creation and public identifier lookup.
- `organizations.repositories.MembershipRepository`
  Encapsulates membership reads and tenant-sensitive role checks.
- `organizations.repositories.InviteRepository`
  Encapsulates invite creation, listing, status counts, and expiry updates.
- `companies.repositories.CompanyRepository`
  Encapsulates tenant-scoped company reads and writes.
- `people.repositories.PersonRepository`
  Encapsulates tenant-scoped person reads and writes.
- `admin_panel.repositories.AdminAccessLogRepository`
  Encapsulates global access-audit reads, counts, and keyset-based page retrieval.

## Services

- `accounts.services.AccountService`
  Handles registration and authenticated session creation.
- `organizations.services.ActiveOrganizationService`
  Synchronizes tenant context from the session into the request.
- `organizations.services.OrganizationService`
  Creates organizations atomically and switches the active organization safely.
- `organizations.services.InviteService`
  Generates unique invite codes, validates permissions, expires outdated codes, and redeems invites atomically.
- `dashboard.services.DashboardMetricsService`
  Builds tenant-safe summary metrics for the dashboard.
- `companies.services.CompanyService`
  Creates and updates tenant-scoped companies.
- `people.services.PersonService`
  Creates and updates tenant-scoped persons with normalized contact data.
- `admin_panel.services.AdminAuthorizationService`
  Validates membership in the global `Admin` auth group.
- `admin_panel.services.AdminAccessAuditService`
  Records login and logout events with IP address, session key, and actor.
- `admin_panel.middleware.AdminAccessAuditMiddleware`
  Ensures every authenticated session has a current IP audit record and opens a new record when the session IP changes.
- `admin_panel.services.AdminAccessLogPaginationService`
  Resolves keyset-based access log pages with cursor navigation for previous and next slices.
- `dispatch_flow.services.DispatchFlowAccessService`
  Validates whether the active organization has at least one supported dispatch app installed and controls sidebar/page visibility for the unified dispatch screen.
- `dispatch_flow.services.DispatchFlowWorkspaceService`
  Reuses Bot Conversa and Gmail dispatch builders to assemble the unified page without duplicating form logic.
- `dispatch_flow.services.DispatchFlowActionService`
  Delegates Bot Conversa and Gmail dispatch creation to the existing channel-specific business services.
- `bot_conversa.services.*`
  Encapsulates Bot Conversa installation resolution, remote contact sync, tag cache refresh, tag assignment, flow cache refresh, and dispatch processing.
- `hubspot_integration.services.*`
  Encapsulates HubSpot installation resolution, company/contact sync, pipeline refresh, business creation, business-person association, and async business search results for Tom Select.
- `apollo_integration.services.*`
  Encapsulates Apollo installation resolution, remote company search, remote person search, person enrichment, usage snapshots, bulk import into CRM, and optional sync handoff to HubSpot.
- `gmail_integration.services.*`
  Encapsulates Gmail credential handling, template management, email dispatch creation, and paced dispatch processing.

## Views and routes

- `/login/`
- `/register/`
- `/logout/`
- `/onboarding/`
- `/onboarding/create/`
- `/onboarding/join/`
- `/dashboard/`
- `/admin-panel/`
- `/admin-panel/ips/`
- `/fluxo-disparo/`
- `/organizations/`
- `/organizations/switch/`
- `/invites/`
- `/invites/generate/`
- `/apps/`
- `/api-keys/`
- `/companies/`
- `/people/`
- `/apps/bot-conversa/`
- `/apps/hubspot/`
- `/apps/gmail/`
- `/apps/apollo/`

## Navigation flow

1. Register user.
2. Redirect to login.
3. Login user.
4. Redirect to onboarding.
5. User can:
   create organization,
   join by invite code,
   or skip.
6. Dashboard checks tenant context:
   if active organization exists, load tenant summary and installed modules;
   if not, show guidance to create or join an organization.
7. Inside an active tenant, CRM data and integrations resolve only from tenant-scoped repositories and validated services.

## Security points

- All tenant reads come from repositories filtered by the active organization or validated membership.
- Passwords are handled by Django's native password hashers, which use salted hashes so equal passwords do not produce equal stored hashes.
- Emails are encrypted at rest and never relied on directly for uniqueness or lookup in the database.
- Invite generation requires both:
  a valid active organization,
  and a role of `owner` or `admin`.
- `Painel Admin` access requires backend validation that the authenticated user belongs to Django auth group `Admin`.
- Login and logout events are stored in the database with session key, IP, actor, and timestamps for administrative audit.
- Bot Conversa, HubSpot, Gmail, and API key mutation flows require both:
  a valid active organization,
  and a manager-capable membership.
- Invite redemption validates:
  code format,
  code existence,
  expiration,
  usage status,
  and existing membership conflicts.
- Organization switching never trusts client input alone; it always validates membership.
- Public UUID identifiers avoid exposing sequential IDs in switching flows.

## Current implementation focus

1. Tenant foundation
   Custom user, organization models, memberships, invites, session-backed active organization, and middleware.
2. CRM foundation
   Tenant-scoped companies and people with normalized contact data and integration identifiers.
3. Integration platform
   App catalog, installations, encrypted credentials, secure reveal flow, and access audit.
4. Operational modules
   Apollo company search/import, Apollo person search/enrichment, Bot Conversa tag synchronization/assignment and flow dispatches, HubSpot sync/business workflows, and Gmail templates/dispatches with configurable pacing and async audience filters for people who have not yet received sends in each channel.
5. Next evolution
   Stronger model-level tenant consistency guarantees, broader audit coverage, background processing options, and richer CRM workflows.
