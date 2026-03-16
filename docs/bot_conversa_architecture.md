# Bot Conversa Architecture

## Suggested architecture

- `people` stores internal CRM persons scoped to one organization.
- `bot_conversa` owns the external integration domain: contact links, flow cache, sync logs, and dispatch jobs.
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
- Stores:
  - `phone`
  - `normalized_phone`
  - `first_name`
  - `last_name`
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

### `bot_conversa.BotConversaSyncLog`

- Audit trail for contact verification and creation.
- Stores action, outcome, actor, person, local link, and remote payload metadata.

### `bot_conversa.BotConversaFlowDispatch`

- Parent job record for a flow send operation.
- Stores organization, installation, selected flow, lifecycle status, counters, and timestamps.

### `bot_conversa.BotConversaFlowDispatchItem`

- Per-contact execution record inside a dispatch.
- Stores target person snapshot, phone, subscriber id, item status, attempts, sent time, and error message.

## Relationships

- `Organization 1:N Person`
- `Organization 1:N BotConversaContact`
- `Person 1:N BotConversaContact`
- `OrganizationAppInstallation 1:N BotConversaContact`
- `OrganizationAppInstallation 1:N BotConversaFlowCache`
- `BotConversaFlowCache 1:N BotConversaFlowDispatch`
- `BotConversaFlowDispatch 1:N BotConversaFlowDispatchItem`

## Permissions

- `owner`
  Full Bot Conversa access.
- `admin`
  Full Bot Conversa operational access.
- `user`
  Can view module pages, but cannot create persons, sync contacts, refresh flows, or create/process dispatches.

## Services

- `BotConversaInstallationService`
  Resolves the active app installation and loads the API key from encrypted credentials in the database.
- `BotConversaPeopleService`
  Creates tenant-scoped internal persons.
- `BotConversaContactSyncService`
  Searches Bot Conversa by phone, creates contacts when missing, and stores the local link.
- `BotConversaFlowService`
  Refreshes the local flow cache.
- `BotConversaRemoteContactService`
  Loads live remote contacts and enriches them with local link information.
- `BotConversaDispatchService`
  Creates dispatch jobs and processes pending items in safe batches.

## Repositories

- `PersonRepository`
- `BotConversaContactRepository`
- `BotConversaFlowCacheRepository`
- `BotConversaSyncLogRepository`
- `BotConversaFlowDispatchRepository`
- `BotConversaFlowDispatchItemRepository`

## Bot Conversa client

- `bot_conversa.client.BotConversaClient`
  Encapsulates HTTP requests, error handling, and response normalization.
- Base URL comes from `NephewCRM/.env` through `BOT_CONVERSA_API_BASE_URL`.
- Endpoint paths are centralized in `bot_conversa/constants.py` and aligned with the validated Bot Conversa webhook contract:
  - `/api/v1/webhook/flows/`
  - `/api/v1/webhook/subscriber/`
  - `/api/v1/webhook/subscriber/get_by_phone/{phone}/`
  - `/api/v1/webhook/subscriber/{subscriber_id}/send_flow/`
- API key is never loaded from `.env` inside business logic; it always comes from `integrations` credentials for the active organization.

## Navigation flow

1. The sidebar `Apps` dropdown is built from installed apps of the active organization only.
2. If Bot Conversa is installed, it appears in the dropdown.
3. Clicking it opens the Bot Conversa module.
4. Inside the module, sub-navigation separates:
   - Overview
   - Persons
   - Contacts
   - Flows
   - Dispatches

## Contact synchronization flow

1. User selects a person from the active organization.
2. Backend validates tenant and operator role.
3. Backend loads the Bot Conversa API key from the database.
4. Backend searches the remote contact by normalized phone.
5. If found:
   the local link is updated with the returned subscriber id.
6. If not found:
   backend creates the remote contact and then stores the local link.
7. Sync logs are recorded without exposing secrets.

## Flow list flow

1. User opens the flows page.
2. Cached flows are listed from the local database.
3. Owner or admin can refresh the cache.
4. Refresh uses the active organization credential and updates or inserts local flow cache rows.

## Flow dispatch flow

1. Owner or admin selects a cached flow.
2. Owner or admin selects one or more internal persons.
3. Backend creates one dispatch job and one item per person.
4. The dispatch detail page polls a backend endpoint.
5. Each poll processes a small batch:
   - ensure remote subscriber exists
   - create if missing
   - send the flow
   - persist success or failure per item
6. Progress is computed from persisted item status counters.

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
