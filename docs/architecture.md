# Nephew CRM Architecture

## Suggested architecture

- `core`: project settings, global URL routing, environment-level wiring.
- `common`: shared abstractions such as timestamps, public identifiers, Bootstrap form helpers, middleware, and generic mixins.
- `accounts`: custom user model, registration, login, logout, and account-focused services.
- `organizations`: tenant domain, memberships, invite codes, onboarding, organization switching, and permission-sensitive services.
- `dashboard`: authenticated application pages that depend on the active organization context.

## Folder structure

```text
NephewCRM/
├─ core/
├─ common/
├─ accounts/
├─ organizations/
├─ dashboard/
├─ templates/
│  └─ partials/
├─ static/
│  ├─ css/
│  └─ js/
└─ docs/
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

## Roles and permissions

- `owner`
  Highest organization role. Can manage invites, members, and organization-level actions.
- `admin`
  Can manage invites and tenant-scoped operational actions inside the active organization.
- `user`
  Can access tenant data allowed by future modules, but cannot create invite codes.

## Multi-tenancy decisions

- Strategy: shared schema with row-level tenant isolation.
- Active tenant source: `active_organization_id` in session.
- Request resolution: middleware loads `request.active_organization` and `request.active_membership`.
- Safe switching: only via POST to `organizations/switch/` after validating membership.
- Fallback behavior: when a user has memberships but no active organization in session, the middleware selects the first valid membership.
- No access: when a user has no memberships, dashboard renders an empty state instead of tenant data.

## Repositories

- `accounts.repositories.UserRepository`
  Encapsulates account creation and email lookup.
- `organizations.repositories.OrganizationRepository`
  Encapsulates organization creation and public identifier lookup.
- `organizations.repositories.MembershipRepository`
  Encapsulates all membership reads, counts, and tenant-scoped member lists.
- `organizations.repositories.InviteRepository`
  Encapsulates invite creation, listing, status counts, and expiry updates.

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

## Views and routes

- `/login/`
- `/register/`
- `/logout/`
- `/onboarding/`
- `/onboarding/create/`
- `/onboarding/join/`
- `/dashboard/`
- `/apps/`
- `/api-keys/`
- `/organizations/`
- `/organizations/switch/`
- `/invites/`
- `/invites/generate/`

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
   if active organization exists, load tenant summary;
   if not, show guidance to create or join an organization.

## Security points

- All tenant reads come from repositories filtered by the active organization or validated membership.
- Passwords are handled by Django's native password hashers, which use salted hashes so equal passwords do not produce equal stored hashes.
- Emails are encrypted at rest and never relied on directly for uniqueness or lookup in the database.
- Invite generation requires both:
  a valid active organization,
  and a role of `owner` or `admin`.
- Invite redemption validates:
  code format,
  code existence,
  expiration,
  usage status,
  and existing membership conflicts.
- Organization switching never trusts client input alone; it always validates membership.
- Public UUID identifiers avoid exposing sequential IDs in switching flows.

## Initial implementation stages

1. Tenant foundation
   Custom user, organization models, memberships, invites, session-backed active organization, middleware.
2. Access flow
   Registration, login, logout, onboarding, create organization, join by invite, dashboard empty state.
3. Workspace shell
   Sidebar, navbar, theme toggle, organizations page, invites page, apps placeholder, API keys placeholder.
4. Next stage
   App catalog, CRM entities, permissions expansion, audit logging, secure API key storage, pipelines, and integrations.
