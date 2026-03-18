# Integrations and API Keys Architecture

## Suggested architecture

- `integrations` is the bounded context for external app catalog, tenant app installations, credentials, and credential access audit.
- `organizations` remains the source of tenant identity, memberships, and role evaluation.
- `common` provides reusable encryption primitives, tenant-aware mixins, and shared model mixins.
- `dashboard` and tenant-facing modules such as `apollo_integration`, `bot_conversa`, `hubspot_integration`, and `gmail_integration` consume the active organization already resolved by middleware.

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
- Belongs to one `OrganizationAppInstallation`; tenant ownership is derived through the installation relation.
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
  Generates a safe preview while preserving a useful prefix when possible.

## Integration interplay

- `apollo_integration`, `hubspot_integration`, `bot_conversa`, and `gmail_integration` are independent operational modules. They do not need direct runtime calls into each other to work.
- The shared dependency is the tenant-scoped CRM core, especially `people.Person`, company relations, and the common matching helpers.
- Apollo atualmente interage com o CRM por meio de `companies.Company`, nao de `people.Person`, porque esta primeira fase cobre apenas empresas.
- HubSpot and Bot Conversa therefore interoperate through shared people records:
  - one contact can be imported from HubSpot and later receive a Bot Conversa flow
  - one remote Bot Conversa contact can be saved in the CRM and later be enriched with HubSpot identifiers
- The current unification is partial, not a dedicated identity graph:
  - `Person` stores fixed provider identifiers such as `hubspot_contact_id` and `bot_conversa_id`
  - `common.matching` can reconcile by provider id, normalized email, normalized phone, `name + email`, and `name + phone`
  - fallback matching by name alone still exists, which helps reduce duplicates but is a weaker merge signal
- This means the modules are independent as apps, but not independent as tenant data.

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

### Gmail dispatch flow

1. Owner or admin opens the Gmail module inside the active organization.
2. User selects a saved template and one or more tenant-scoped persons with email.
3. User can define a configurable min/max delay interval for pacing the email sends.
4. Backend creates one dispatch record and one recipient record per selected person.
5. The dispatch detail page polls a backend endpoint.
6. Each processing cycle sends a safe batch of pending recipients and updates terminal counters.
7. When a delay interval is configured, the frontend waits a randomized value between the configured min and max before the next processing step.
8. The dispatch creation screen can asynchronously filter the audience to only show people who have not yet received a Gmail send in that tenant.

### Apollo company import flow

1. Owner or admin installs Apollo and saves an API key in the active organization.
2. User opens the Apollo companies screen.
3. Backend sends tenant-safe filters to the Apollo company search endpoint.
4. The remote response is normalized into a common local shape.
5. The screen shows whether each remote company already exists in the CRM and whether the linked local company is already synced with HubSpot.
6. Owner or admin can select multiple rows and save them into the local CRM.
7. The import service either updates a matched local company or creates a new tenant-scoped company.
8. Every import is logged, and usage data can be snapshotted for later display.

### Bot Conversa dispatch flow

1. Owner or admin opens the Bot Conversa module inside the active organization.
2. User selects a cached flow and one or more tenant-scoped persons.
3. User can define a configurable min/max delay interval for pacing the sends.
4. Backend creates one dispatch record and one item record per selected person.
5. The dispatch detail page polls a backend endpoint.
6. Each processing cycle claims a safe batch of pending items, ensures a remote subscriber exists, and triggers the flow.
7. `running` items are not counted as complete, which avoids premature dispatch completion under concurrent polling.
8. The dispatch creation screen can asynchronously filter the audience to only show people who have not yet received a successful WhatsApp send in that tenant.

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
- Some tenant consistency guarantees also rely on service-layer validation where models reference other tenant-scoped records indirectly.
- Apollo segue o mesmo padrao: a API key fica em `integrations`, enquanto o resultado remoto so se torna duravel depois de ser mapeado para `Company` dentro do tenant ativo.

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
