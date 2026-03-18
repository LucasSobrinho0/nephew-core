# Bot Conversa Architecture

## Suggested architecture

- `people` stores internal CRM persons scoped to one organization.
- `bot_conversa` owns the external integration domain: contact links, tag cache, flow cache, sync logs, and dispatch jobs.
- `integrations` remains the source of installed apps and encrypted API credentials.
- `organizations` continues to resolve the active tenant and role context.

## Django apps and folder structure

```text
people/
  admin.py
  forms.py
  models.py
  repositories.py
  services.py
  tests.py

bot_conversa/
  admin.py
  client.py
  constants.py
  exceptions.py
  forms.py
  models.py
  repositories.py
  services.py
  tests.py
  urls.py
  views.py
  templates/
    bot_conversa/
```

## Domain model

### `people.Person`

- Internal CRM person table.
- Tenant-scoped with `organization`.
- Stores core CRM identity and communication fields, including:
  - `phone`
  - `normalized_phone`
  - `email`
  - `email_lookup`
  - `first_name`
  - `last_name`
  - integration identifiers such as `bot_conversa_id` and `hubspot_contact_id`
  - optional `company`
  - `is_active`
  - `created_by`
  - `updated_by`
  - `created_at`
  - `updated_at`
- Unique phone per organization after normalization.

### `bot_conversa.BotConversaContact`

- Local link between one internal `Person` and one remote Bot Conversa subscriber.
- Stores:
  - `organization`
  - `installation`
  - `person`
  - `external_subscriber_id`
  - `external_name`
  - `phone`
  - `normalized_phone`
  - `sync_status`
  - `last_synced_at`
  - `last_error_message`
  - `remote_payload`
- Prevents duplicate links per person and duplicate subscriber ids per organization.

### `bot_conversa.BotConversaFlowCache`

- Hybrid cache for remote flows.
- Stores:
  - `organization`
  - `installation`
  - `external_flow_id`
  - `name`
  - `status`
  - `description`
  - `last_synced_at`
  - `raw_payload`
- Avoids live dependency on every render of the flow select.

### `bot_conversa.BotConversaTag`

- Local cache of remote Bot Conversa tags.
- Stores:
  - `organization`
  - `installation`
  - `external_tag_id`
  - `name`
  - `last_synced_at`
  - `raw_payload`
- Allows the CRM to reuse remote tag audiences without querying the API on every screen render.

### `bot_conversa.BotConversaPersonTag`

- Local link between one internal `Person`, one remote Bot Conversa tag, and the resolved subscriber used in that association.
- Stores:
  - `organization`
  - `installation`
  - `person`
  - `tag`
  - `contact_link`
  - `external_subscriber_id`
  - `sync_status`
  - `last_synced_at`
  - `last_error_message`
  - `remote_payload`
- Prevents duplicate tag assignments for the same person inside one tenant.

### `bot_conversa.BotConversaSyncLog`

- Audit trail for contact verification, creation, CRM import, and linking.
- Stores action, outcome, actor, person, local link, and remote payload metadata.

### `bot_conversa.BotConversaFlowDispatch`

- Parent job record for a flow send operation.
- Stores organization, installation, selected flow, lifecycle status, counters, timestamps, and a configurable min/max delay interval between polls when the operator wants to pace WhatsApp sends.

### `bot_conversa.BotConversaFlowDispatchItem`

- Per-contact execution record inside a dispatch.
- Stores target person snapshot, phone, subscriber id, item status, attempts, sent time, and error message.

## Relationships

- `Organization 1:N Person`
- `Organization 1:N BotConversaContact`
- `Person 1:N BotConversaContact`
- `OrganizationAppInstallation 1:N BotConversaContact`
- `OrganizationAppInstallation 1:N BotConversaFlowCache`
- `OrganizationAppInstallation 1:N BotConversaTag`
- `BotConversaFlowCache 1:N BotConversaFlowDispatch`
- `BotConversaFlowDispatch 1:N BotConversaFlowDispatchItem`
- `BotConversaTag 1:N BotConversaPersonTag`
- `Person 1:N BotConversaPersonTag`

## Permissions

- `owner`
  Full Bot Conversa access.
- `admin`
  Full Bot Conversa operational access.
- `user`
  Can view module pages, but cannot create persons, sync contacts, refresh flows, save remote contacts into CRM, or create/process dispatches.

## Services

- `BotConversaInstallationService`
  Resolves the active app installation and loads the API key from encrypted credentials in the database.
- `BotConversaPeopleService`
  Creates tenant-scoped internal persons.
- `BotConversaContactSyncService`
  Searches Bot Conversa by phone, creates contacts when missing, and stores the local link.
- `BotConversaRemoteContactService`
  Loads live remote contacts, enriches them with local link information, and saves selected contacts into the local CRM.
- `BotConversaFlowService`
  Refreshes the local flow cache.
- `BotConversaTagService`
  Refreshes remote tags, builds local tag summaries, and assigns selected persons to remote subscribers under one tenant.
- `BotConversaDispatchService`
  Creates dispatch jobs and processes pending items while respecting terminal item counters and configured pacing.

## Repositories

- `PersonRepository`
- `BotConversaContactRepository`
- `BotConversaFlowCacheRepository`
- `BotConversaTagRepository`
- `BotConversaPersonTagRepository`
- `BotConversaSyncLogRepository`
- `BotConversaFlowDispatchRepository`
- `BotConversaFlowDispatchItemRepository`

## Bot Conversa client

- `bot_conversa.client.BotConversaClient`
  Encapsulates HTTP requests, error handling, and response normalization.
- Base URL comes from `NephewCRM/.env` through `BOT_CONVERSA_API_BASE_URL`.
- Endpoint paths are centralized in `bot_conversa/constants.py`.
- API key is never loaded from `.env` inside business logic; it always comes from `integrations` credentials for the active organization.

## Navigation flow

1. The sidebar `Apps` dropdown is built from installed apps of the active organization only.
2. If Bot Conversa is installed, it appears in the dropdown.
3. Clicking it opens the Bot Conversa module.
4. Inside the module, sub-navigation separates:
   - Dashboard
   - People
   - Contacts
   - Tags
   - Flows
   - Dispatches

## Tag synchronization flow

1. Owner or admin opens the tags page.
2. Backend loads the active organization Bot Conversa credential.
3. Backend calls `GET /tags/` and refreshes the tenant-scoped local cache.
4. The page shows each cached tag with the current count of linked internal people.

## Tag assignment flow

1. Owner or admin selects one cached tag and one or more internal people.
2. Backend validates tenant and operator role.
3. For each person, backend ensures the remote subscriber exists.
4. Backend calls `POST /subscriber/{subscriber_id}/tags/{tag_id}/`.
5. Backend stores or updates the local `BotConversaPersonTag` link for future filtering and dispatch use.

## Contact synchronization flow

1. User selects a person from the active organization.
2. Backend validates tenant and operator role.
3. Backend loads the Bot Conversa API key from the database.
4. Backend searches the remote contact by normalized phone.
5. If found:
   the local link is updated with the returned subscriber id and the remote tags are synchronized into the local Bot Conversa tag cache plus the person-tag links.
6. If not found:
   backend creates the remote contact and then stores the local link.
7. Sync logs are recorded without exposing secrets.

## Remote contact save flow

1. User loads remote contacts from the active organization installation.
2. Owner or admin selects one or more remote contacts to save in the CRM.
3. Backend tries to match an existing person by integration id, phone, or other local indexes.
4. If no match exists:
   a new tenant-scoped `Person` is created.
5. Backend creates or updates the `BotConversaContact` local link.
6. Sync logs keep the final `contact_link` reference for auditability.

## Flow list flow

1. User opens the flows page.
2. Cached flows are listed from the local database.
3. Owner or admin can refresh the cache.
4. Refresh uses the active organization credential and updates or inserts local flow cache rows.

## Flow dispatch flow

1. Owner or admin selects a cached flow.
2. Owner or admin selects one or more internal persons on the dispatch screen.
3. Owner or admin optionally defines a min/max delay interval in seconds.
4. Backend creates one dispatch job and one item per resolved person.
5. The dispatch detail page polls a backend endpoint.
6. When a delay interval is configured, the frontend waits a randomized value between the configured min and max before requesting the next processing step.
7. Each processing cycle:
   - ensures the remote subscriber exists
   - creates it if missing
   - sends the flow
   - persists success or failure per item
8. Progress is computed from terminal item status counters only; `running` items do not count as completed.
9. The dispatch creation screen can asynchronously filter the audience to only show people who have not yet received a successful WhatsApp send in the active tenant.

## Status update strategy

- Current phase uses backend polling with persisted job and item records.
- No background thread is required.
- If the user leaves the page, processing can resume later without losing state.
- This is intentionally compatible with a future queue worker migration.

## Multi-tenancy and security points

- Every model is organization-scoped directly or through installation plus organization.
- Every view validates the active organization and installed app before rendering or mutating.
- Sensitive actions require `owner` or `admin`.
- Dispatch and sync endpoints never trust raw organization identifiers from the client.
- Bot Conversa API key is decrypted only in backend services when an outbound request is about to happen.
- API key is never rendered in HTML, JavaScript, messages, or logs.
- Phone numbers are normalized consistently before uniqueness checks and API calls.
- Cross-tenant resources resolve by organization plus public identifier, not by global ids alone.
- Tenant isolation in this module is enforced primarily in views, repositories, and services; model-level foreign keys do not encode every cross-field tenant consistency rule by themselves.
