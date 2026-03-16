# Integrations and API Keys Architecture

## Suggested architecture

- `integrations` is the bounded context for external app catalog, tenant app installations, credentials, and credential access audit.
- `organizations` remains the source of tenant identity, memberships, and role evaluation.
- `common` provides reusable encryption primitives, tenant-aware mixins, and shared model mixins.
- `dashboard` and future CRM modules consume the active organization already resolved by middleware.

## Django app structure

```text
integrations/
  admin.py
  apps.py
  constants.py
  forms.py
  models.py
  repositories.py
  services.py
  tests.py
  urls.py
  views.py
  migrations/
  templates/
    integrations/
      apps.html
      api_keys.html
```

## Domain model

### `integrations.AppCatalog`

- Global catalog of supported integrations.
- One row per app code such as `apollo`, `hubspot`, `gmail`, and `bot_conversa`.
- Stores UI metadata like `name`, `description`, `icon_class`, and capability flags like `supports_api_key`.

### `integrations.OrganizationAppInstallation`

- Tenant-scoped installation record.
- Connects one `Organization` to one `AppCatalog` entry.
- Stores lifecycle status and audit ownership fields.
- Enforces uniqueness on `(organization, app)`.

### `integrations.OrganizationAppCredential`

- Tenant-scoped credential record for one installed app.
- Belongs to one `OrganizationAppInstallation`.
- Stores `secret_value` encrypted at rest.
- Stores `masked_value`, `last_four`, `version`, `status`, `created_by`, `updated_by`, `revoked_by`, and `revoked_at`.
- Enforces:
  - unique credential version per installation and credential type
  - only one active credential per installation and credential type

### `integrations.AppCredentialAccessAudit`

- Immutable audit trail for sensitive reveal attempts.
- Stores actor, organization, app, installation, credential, event type, outcome, reason, IP, and user agent.

## Relationships

- `Organization 1:N OrganizationAppInstallation`
- `AppCatalog 1:N OrganizationAppInstallation`
- `OrganizationAppInstallation 1:N OrganizationAppCredential`
- `OrganizationAppCredential 1:N AppCredentialAccessAudit`
- `Organization 1:N AppCredentialAccessAudit`

## Constraints and consistency rules

- One installation per organization and app.
- One active API key per installation.
- Credential versions are append-only.
- All reads and writes resolve from the active organization, never from raw client organization input.
- Reveal endpoints use installation `public_id`, not sequential primary keys.

## Permissions

- `owner`
  Can install apps, save API keys, rotate API keys, and reveal API keys inside the active organization.
- `admin`
  Same permissions as `owner` for integrations and API keys.
- `user`
  Can access tenant-safe workspace areas but cannot open API Keys, save credentials, or reveal them.

## Services

- `IntegrationAuthorizationService`
  Validates membership and manager role in the active organization.
- `IntegrationCatalogService`
  Builds the catalog state combining global apps with tenant installations and current credentials.
- `AppInstallationService`
  Installs or reactivates apps for the active organization.
- `AppCredentialService`
  Saves API keys, rotates versions, validates reveal confirmation, and writes audit events.
- `AppMaskingService`
  Generates a safe preview like `sk_live ********ABCD`.

## Repositories

- `AppCatalogRepository`
  Global catalog reads.
- `AppInstallationRepository`
  Tenant-filtered installation reads and writes.
- `AppCredentialRepository`
  Current credential lookup, versioning, and deactivation helpers.
- `AppCredentialAccessAuditRepository`
  Audit persistence only.

## Views, forms, templates, and URLs

- `/apps/`
  Catalog view for the active organization.
- `/apps/install/`
  POST endpoint to install an app in the active organization.
- `/api-keys/`
  Management screen restricted to `owner` and `admin`.
- `/api-keys/save/`
  POST endpoint to save or rotate the API key for one installed app.
- `/api-keys/installations/<installation_public_id>/reveal/`
  POST-only JSON endpoint that returns the decrypted key only after backend validation.

Forms:

- `AppInstallForm`
- `ApiKeySaveForm`
- `ApiKeyRevealForm`

Templates:

- `integrations/apps.html`
- `integrations/api_keys.html`

## Navigation and interface flow

### App installation flow

1. User enters `Apps` or `API Keys`.
2. System resolves `request.active_organization` and `request.active_membership`.
3. Catalog shows install action only when the app is not installed.
4. `owner` or `admin` submits installation.
5. Backend validates active tenant and role, then creates or reactivates the installation.

### API key save flow

1. User opens `API Keys`.
2. Only installed apps render the API key form.
3. User submits a new key.
4. Backend validates tenant, role, installation ownership, and app capability.
5. Secret is encrypted before storage.
6. Existing active credential is deactivated and a new version becomes active.
7. UI only shows masked output, never the full secret.

### Secure reveal flow

1. User clicks the eye icon.
2. Frontend opens a modal and asks for the exact word `mostrar`.
3. Frontend does not have the secret and does not request it until the modal form is submitted.
4. Backend validates:
   - authenticated user
   - active organization
   - active membership in that organization
   - role `owner` or `admin`
   - installation belongs to the active organization
   - confirmation word exactly matches `mostrar`
5. Only then the backend returns the decrypted key in a no-store JSON response.
6. Every reveal attempt is audited as `success`, `denied`, or `not_found`.

## Encryption strategy

- API keys use `EncryptedTextField` with a dedicated encryption purpose: `app-credential`.
- The encryption source order is:
  - `APP_CREDENTIAL_ENCRYPTION_KEY`
  - `FIELD_ENCRYPTION_KEY`
  - `SECRET_KEY`
- This allows credential secrets to be isolated from other encrypted fields.
- The field supports fallback decryption from the default purpose for safe migration scenarios.

## Encryption key handling

- Store `APP_CREDENTIAL_ENCRYPTION_KEY` in environment variables or a secrets manager, never in Git.
- Recommended production storage:
  - cloud secret manager
  - container runtime secret
  - CI/CD injected environment variable
- Do not print the key in startup logs, settings dumps, or debug pages.

## Rotation strategy

- Short term:
  keep `APP_CREDENTIAL_ENCRYPTION_KEY` stable and rotate only in planned maintenance windows.
- Safer future evolution:
  move to a keyring model with key version metadata and background re-encryption.
- Practical rotation path from the current base:
  1. add a new active key in environment
  2. keep previous key as fallback decryptor
  3. run a management command that re-saves credentials
  4. remove the old fallback after verification

## Masking strategy

- Never show the full secret in list or initial page render.
- Persist `masked_value` and `last_four` to avoid decrypting secrets just to build list views.
- Default preview format:
  `prefix ********LAST4`

## Audit strategy

- Minimal audit implemented:
  - `created_at`
  - `updated_at`
  - `created_by`
  - `updated_by`
  - reveal access audit rows with actor, outcome, reason, IP, and user agent
- Future improvements:
  - explicit revoke action
  - rotation reason
  - secret validation checks against vendor APIs

## Multi-tenancy decisions

- Strategy: shared schema with strict row filtering.
- Tenant context source: active organization in session.
- Request context:
  - `request.active_organization`
  - `request.active_membership`
- No view trusts client-provided organization identifiers for installation or credential writes.
- All repository methods that touch tenant data filter by organization relation.

## Security points

- No raw API key in HTML, hidden inputs, data attributes, template cache, or initial JavaScript.
- Reveal endpoint is POST-only and returns no-store headers.
- UI reveal action is only a trigger; authorization and confirmation validation happen in the backend.
- Cross-tenant installation ids return `404` on reveal to avoid enumeration.
- User role cannot access API Keys page and cannot call reveal successfully.
- Secrets are never included in model string representations, success messages, or list queries.
- Stored secret is encrypted at rest.
- Masked preview is persisted to prevent unnecessary decrypt operations.

## Implementation stages

1. Add `integrations` app with catalog, installation, credential, and audit models.
2. Seed the global app catalog.
3. Add repositories and services for installation, credential persistence, masking, and reveal audit.
4. Add manager-only API Keys UI and tenant-aware app catalog UI.
5. Add secure frontend reveal modal with backend confirmation.
6. Add automated tests for tenant isolation, permission checks, masking, and encryption-at-rest.
