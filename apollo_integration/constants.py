APOLLO_APP_CODE = 'apollo'
APOLLO_API_BASE_URL = 'https://api.apollo.io'
APOLLO_DEFAULT_TIMEOUT_SECONDS = 30
APOLLO_MAX_RESULTS_PER_PAGE = 100
APOLLO_BULK_ENRICH_MAX_BATCH_SIZE = 10
APOLLO_ORGANIZATION_SEARCH_PATH = '/api/v1/mixed_companies/search'
APOLLO_PEOPLE_SEARCH_PATH = '/api/v1/mixed_people/api_search'
APOLLO_BULK_PEOPLE_ENRICH_PATH = '/api/v1/people/bulk_match'
APOLLO_USAGE_STATS_PATH = '/api/v1/usage_stats/api_usage_stats'
APOLLO_HTTP_USER_AGENT = 'NephewCRM Apollo Integration/1.0'

APOLLO_EMPLOYEE_RANGE_CHOICES = (
    ('1,10', '1 a 10'),
    ('11,20', '11 a 20'),
    ('21,50', '21 a 50'),
    ('51,100', '51 a 100'),
    ('101,200', '101 a 200'),
    ('201,500', '201 a 500'),
    ('501,1000', '501 a 1000'),
    ('1001,2000', '1001 a 2000'),
    ('2001,5000', '2001 a 5000'),
    ('5001,10000', '5001 a 10000'),
)

APOLLO_INDUSTRY_CHOICES = (
    ('farming', 'Agricultura'),
    ('logistics & supply chain', 'Logistica e cadeia de suprimentos'),
    ('retail', 'Varejo'),
    ('food & beverages', 'Alimentos e bebidas'),
    ('health, wellness & fitness', 'Saude, bem-estar e fitness'),
    ('transportation/trucking/railroad', 'Transporte, cargas e ferroviario'),
    ('utilities', 'Servicos publicos'),
    ('oil & energy', 'Oleo e energia'),
    ('environmental services', 'Servicos ambientais'),
)

APOLLO_COUNTRY_CHOICES = (
    ('', 'Qualquer pais'),
    ('Brazil', 'Brasil'),
    ('United States', 'Estados Unidos'),
    ('Canada', 'Canada'),
    ('Mexico', 'Mexico'),
    ('Argentina', 'Argentina'),
    ('Chile', 'Chile'),
    ('Colombia', 'Colombia'),
    ('Peru', 'Peru'),
    ('Uruguay', 'Uruguai'),
    ('Paraguay', 'Paraguai'),
    ('Bolivia', 'Bolivia'),
    ('Ecuador', 'Equador'),
    ('Venezuela', 'Venezuela'),
    ('Portugal', 'Portugal'),
    ('Spain', 'Espanha'),
    ('United Kingdom', 'Reino Unido'),
    ('Germany', 'Alemanha'),
    ('France', 'Franca'),
    ('Italy', 'Italia'),
    ('Netherlands', 'Paises Baixos'),
    ('Australia', 'Australia'),
)

APOLLO_PERSON_TITLE_CHOICES = (
    ('fp&a manager', 'FP&A Manager'),
    ('fpa manager', 'FPA Manager'),
    ('fp and a manager', 'FP and A Manager'),
    ('financial supervisor', 'Supervisor Financeiro'),
    ('it manager', 'Gerente de TI'),
)
