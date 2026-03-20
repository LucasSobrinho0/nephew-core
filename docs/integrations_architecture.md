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
- `hubspot_integration` now also keeps a local business layer for HubSpot deals, including pipeline-stage cache and local person associations per business.
- The shared dependency is the tenant-scoped CRM core, especially `people.Person`, company relations, and the common matching helpers.
- Apollo agora interage com o CRM por meio de `companies.Company` e `people.Person`.
- `dispatch_flow` funciona como uma camada de orquestracao de tela com audiencia unica do CRM, selecao por canal, validacao de elegibilidade por pessoa, preservacao da mesma selecao em erros de contato, preflight opcional de etiquetas do Bot Conversa, preflight opcional de sincronizacao/criacao de negocio no HubSpot, e criacao multicanal de disparos quando um ou ambos os apps estiverem instalados.
- A camada de HubSpot valida remotamente se empresas e contatos ja estao associados a negocios antes de abrir fluxos de sincronizacao com criacao de novo negocio, para que o espelho local reflita o estado real do HubSpot.
- O CRM agora tambem suporta importacao XLSX em background para pessoas e empresas, com jobs por linha, progresso visual e download de modelos operados no servidor.
- A busca de pessoas do Apollo salva resultados censurados no CRM por `apollo_person_id`, sem depender de enrichment nesta fase.
- O enrichment de pessoas do Apollo opera sobre `people.Person` ja sincronizadas e atualiza nome completo e email no proprio registro local.
- Quando o operador marca `Pegar telefone`, o Apollo passa a responder pelo webhook HTTPS do proprio Nephew CRM.
- HubSpot and Bot Conversa therefore interoperate through shared people records:
  - one contact can be imported from HubSpot and later receive a Bot Conversa flow
  - one remote Bot Conversa contact can be saved in the CRM and later be enriched with HubSpot identifiers
- The current unification is partial, not a dedicated identity graph:
  - `Person` stores fixed provider identifiers such as `hubspot_contact_id` and `bot_conversa_id`
  - `common.matching` can reconcile by provider id, normalized email, normalized phone, `name + email`, and `name + phone`
  - fallback matching by name alone still exists, which helps reduce duplicates but is a weaker merge signal
- This means the modules are independent as apps, but not independent as tenant data.
- O processamento de disparos do Bot Conversa pode ser executado em background pela management command `run_bot_conversa_dispatch_worker`, sem depender de manter a tela de status aberta.

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
9. Template variables are documented only on the template authoring screens, not on the dispatch screens, to keep the send workflow focused on audience and pacing.

### HubSpot company sync with remote funnel validation

1. Owner or admin opens the HubSpot companies screen inside the active organization.
2. The local company list resolves whether each company is already in a remote HubSpot funnel by checking remote deal associations for the matched or synced company.
3. The operator can select one or more local companies and optionally request immediate business creation.
4. When business creation is requested, the operator must choose a pipeline and a stage.
5. If any selected company is already associated with one or more remote HubSpot deals, the backend prepares a confirmation step before continuing.

### Dispatch-flow HubSpot preflight

1. Owner or admin opens the unified dispatch-flow screen inside the active organization.
2. The operator selects a CRM audience and chooses WhatsApp, Gmail, or both.
3. If HubSpot is installed for the active organization, the dispatch flow opens a dedicated preflight modal before the dispatch is created.
4. The modal offers a simple branch:
   - continue without HubSpot,
   - or sync pending CRM companies and contacts to HubSpot before the dispatch.
5. If the operator also wants a new HubSpot business, the same preflight collects:
   - whether the business will be centered on a company or on one selected person,
   - the pipeline and stage,
   - and the local contacts that should be attached to the business when the company-centered flow is chosen.
6. The backend only syncs the companies and people that still do not have HubSpot identifiers, so the dispatch flow does not duplicate already-synced entities.
7. When the business is company-centered, the UI preselects the most likely local company and suggests the local contacts already present in the audience; if no selected person is linked locally to that company, the modal warns the operator and still allows selecting local contacts explicitly.
8. When the business is person-centered, the operator chooses one selected local person; that flow requires the chosen person to already be linked to a local company because the local HubSpot business model is company-anchored.
9. After the optional HubSpot steps finish, the unified dispatch flow proceeds with Bot Conversa and/or Gmail dispatch creation and redirects to the consolidated dispatch status screen.
6. After confirmation, the backend syncs the selected companies and then creates one new business per company in the chosen pipeline stage.

### HubSpot person attach-to-business flow

1. Owner or admin opens the HubSpot people screen inside the active organization.
2. The local people list resolves whether each person is already in a remote HubSpot funnel by checking remote deal associations for the matched or synced contact.
3. The operator can use the attach workflow to link an existing local person to an existing local HubSpot business.
4. Backend validation ensures the person, business, and company all belong to the same tenant and remain company-consistent.
5. If needed, the backend first syncs the company and the contact to HubSpot and only then creates the remote contact-to-business association.

### Apollo company import flow

1. Owner or admin installs Apollo and saves an API key in the active organization.
2. User opens the Apollo companies screen.
3. Backend sends tenant-safe filters to the Apollo company search endpoint.
4. The remote response is normalized into a common local shape.
5. The screen shows whether each remote company already exists in the CRM and whether the linked local company is already synced with HubSpot.
6. Owner or admin can select multiple rows and save them into the local CRM.
7. The import service either updates a matched local company or creates a new tenant-scoped company.
8. Every import is logged, and usage data can be snapshotted for later display.

### Apollo people search flow

1. Owner or admin opens the Apollo people screen inside the active organization.
2. User can search by empresa local opcional, nome ou dominio de empresa, cargos e palavras-chave.
3. Backend calls `mixed_people/api_search`.
4. Apollo returns censored person records such as `last_name_obfuscated`, `has_email`, and `has_direct_phone`.
5. The screen shows those results and whether each person is already linked to a local `Person`.
6. Owner or admin can save one or more results into the tenant-scoped CRM.
7. The saved local person keeps `apollo_person_id` and can remain without phone until a later enrichment or reconciliation step.

### Apollo people enrichment flow

1. Owner or admin opens the Apollo enrichment screen inside the active organization.
2. The screen lists only local CRM people that already have `apollo_person_id`.
3. The user selects one or more people and starts enrichment.
4. Backend calls Apollo bulk people enrichment in batches, keyed by `apollo_person_id`.
5. Returned full name and email update the same tenant-scoped `people.Person` rows.
6. If the operator requests phone reveal, Nephew CRM creates a local webhook-backed job and waits for Apollo callback to finish the phone update.

### Bot Conversa dispatch flow

1. Owner or admin opens the Bot Conversa module inside the active organization.
2. User selects a cached flow and one or more tenant-scoped persons.
3. User can define a configurable min/max delay interval for pacing the sends.
4. Backend creates one dispatch record and one item record per selected person.
5. A dedicated worker command can process pending and running dispatches without requiring the detail page to stay open.
6. Each processing cycle claims a safe batch of pending items, ensures a remote subscriber exists, and triggers the flow.
7. When the dispatch has a configured delay interval, the backend stores the next eligible processing time and the worker respects that schedule.
8. `running` items are not counted as complete, which avoids premature dispatch completion under concurrent polling.
9. The dispatch creation screen can asynchronously filter the audience to only show people who have not yet received a successful WhatsApp send in that tenant.

### Unified dispatch flow

1. Owner or admin opens the shared dispatch-flow screen inside the active organization.
2. The screen renders one shared audience list from the local CRM, with delivery eligibility for Gmail and WhatsApp on each person.
3. The operator can filter the audience by people who have not yet received e-mail, WhatsApp, or either channel.
4. If WhatsApp is selected, the backend checks whether the selected people already have Bot Conversa tags.
5. When untagged people are found, the UI opens a reusable selection modal so the operator can continue without tags or apply one or more Bot Conversa tags before the send.
6. The operator selects one list of people and then enables one or both channels.
7. Backend validation blocks the chosen channel if any selected person lacks the required contact data, while preserving the same selected audience on the form.
8. If validation passes, the backend creates one Bot Conversa dispatch, one Gmail dispatch, or both from that same audience selection.

### CRM XLSX import flow

1. Owner or admin opens the local CRM screen for people or companies.
2. The list header exposes a reusable import modal with a server-backed XLSX template download and file upload field.
3. Backend validates the XLSX file, parses the header, stores a local copy, and creates one import job plus one row item per spreadsheet line.
4. The user is redirected to a dedicated job detail page with progress bar, counters, and row-by-row feedback.
5. A background worker command processes pending import rows and updates the job counters.
6. The job detail page polls the backend for progress until the import reaches a terminal state.

### Bot Conversa tags flow

1. Owner or admin opens the Bot Conversa tags page inside the active organization.
2. Backend refreshes the tenant-scoped tag cache from `GET /tags/`.
3. User chooses one synchronized tag and one or more local people.
4. Backend ensures each person has a remote subscriber and then calls `POST /subscriber/{subscriber_id}/tags/{tag_id}/`.
5. The CRM persists the local `person <-> tag` link so later dispatches and filters can reuse the same audience.

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
- Apollo segue o mesmo padrao: a API key fica em `integrations`, enquanto o resultado remoto so se torna duravel depois de ser mapeado para `Company` ou `Person` dentro do tenant ativo.

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
