# Apollo Integration Architecture

## Scope atual

- O app `apollo_integration` cobre apenas empresas nesta primeira fase.
- O modulo permite:
  - consultar empresas remotas no Apollo com filtros
  - visualizar website, segmento, quantidade de funcionarios, email e telefone quando a API retornar
  - selecionar empresas em massa
  - salvar as selecionadas no CRM local
  - sincronizar empresas locais selecionadas com o HubSpot
  - visualizar um resumo de uso da API do Apollo
- O modulo ainda nao cobre:
  - busca de pessoas
  - enrichment de pessoas
  - enrichment de empresas
  - automacoes em background

## Posicionamento no sistema

- `apollo_integration` e um modulo operacional independente, como `hubspot_integration`, `gmail_integration` e `bot_conversa`.
- Ele depende do tenant ativo resolvido por `organizations` e `dashboard`.
- Ele reutiliza o catalogo e o armazenamento de credenciais do app `integrations`.
- Ele reutiliza o CRM local em `companies` para persistir as empresas importadas.
- Ele pode cooperar com o HubSpot por meio da sincronizacao de empresas locais, mas nao depende do HubSpot para funcionar.

## Credenciais

- A autenticacao do Apollo usa API key.
- A chave fica armazenada no fluxo padrao de credenciais por tenant em `integrations.OrganizationAppCredential`.
- O cliente atual envia a chave no header `X-Api-Key`, que e o formato mais compativel com o uso de `master api key` neste projeto.
- O cliente tambem envia `User-Agent` proprio para reduzir bloqueios de borda como Cloudflare 1010 por assinatura HTTP generica.

## Endpoints consumidos

- `POST /api/v1/mixed_companies/search`
  Usado para listar empresas remotas com filtros.
- `POST /api/v1/usage_stats/api_usage_stats`
  Usado para montar o resumo de uso exibido no dashboard.

## Modelo local

### `companies.Company`

- Continua sendo tenant-scoped.
- Passa a armazenar:
  - `apollo_company_id`
  - `email`
  - `segment`
  - `employee_count`
- Mantem tambem:
  - `hubspot_company_id`
  - `website`
  - `phone`
  - `normalized_phone`
- Existe unicidade por tenant em `(organization, apollo_company_id)` quando o valor estiver preenchido.

### `apollo_integration.ApolloCompanySyncLog`

- Registra importacoes do Apollo para o CRM.
- Registra sincronizacoes iniciadas a partir do Apollo em direcao ao HubSpot.
- Guarda actor, outcome, mensagem e payload remoto para auditoria.

### `apollo_integration.ApolloUsageSnapshot`

- Guarda snapshots do uso retornado pela API.
- Permite exibir o ultimo valor salvo quando a consulta online falha.
- Hoje e uma fotografia simples de:
  - payload bruto
  - creditos usados
  - creditos restantes
  - rate limits principais

## Fluxo de busca e importacao

1. Owner ou admin instala o app Apollo e salva a API key.
2. O usuario abre `Apps > Apollo > Empresas`.
3. O frontend envia filtros de busca para o backend.
4. `ApolloCompanyService` monta o payload e chama `ApolloClient`.
5. O cliente normaliza a resposta remota em um shape interno unico.
6. O backend compara os resultados remotos com `companies.Company` do tenant atual.
7. A UI mostra:
   - se a empresa ja existe no CRM
   - se a empresa local correspondente ja esta sincronizada com o HubSpot
8. O usuario marca as empresas desejadas e envia a importacao em massa.
9. O service:
   - vincula a empresa remota a uma empresa local existente quando houver match seguro
   - ou cria uma nova empresa local quando ainda nao houver correspondente
10. O sistema registra `ApolloCompanySyncLog` para auditoria.

## Matching e reutilizacao do CRM

- O modulo nao cria uma tabela paralela de empresas remotas persistidas fora do CRM.
- A empresa salva no Apollo vira ou atualiza uma `companies.Company`.
- O matching reaproveita `common.matching` e considera, nesta ordem:
  - `apollo_company_id`
  - `hubspot_company_id`
  - dominio do website
  - telefone normalizado
  - nome

## Dashboard e uso da API

- O dashboard mostra:
  - quantidade total de empresas do tenant no CRM
  - quantidade de empresas locais que ja tem `apollo_company_id`
  - creditos usados e restantes quando a API retornar esses campos
  - sinais de rate limit retornados pelo Apollo
  - historico recente de importacoes e sincronizacoes
- A API publica do Apollo nao garante um endpoint universal de saldo de creditos restante para todos os planos.
- Por isso o dashboard exibe somente o que estiver presente no payload oficial de `usage_stats`.
- Quando a consulta online falha, o dashboard pode cair para o ultimo snapshot salvo.

## Regras de permissao

- Qualquer usuario autenticado com acesso ao tenant pode abrir telas somente leitura do modulo.
- Apenas `owner` e `admin` podem:
  - operar importacao em massa
  - sincronizar com HubSpot
  - instalar o app
  - alterar a API key

## Decisoes intencionais desta fase

- Pessoas do Apollo ainda nao entram no escopo para evitar misturar busca, match e enrichment cedo demais.
- Enrichment fica para uma fase posterior, porque muda bastante custo, UX e regra de negocio.
- A sincronizacao com HubSpot permanece opcional e parte das empresas locais, nao como dependencia de runtime do Apollo.
