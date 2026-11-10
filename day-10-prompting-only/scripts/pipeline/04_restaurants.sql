-- Raw table loaded first with:
--   carto import --file tripadvisor_european_restaurants.csv.gz --connection cs_bigquery \
--     --destination cartodb-on-gcp-cs-team.paris_restaurants.tripadvisor_european_restaurants_raw --overwrite
-- Cluster the raw European table spatially
CREATE OR REPLACE TABLE `cartodb-on-gcp-cs-team.paris_restaurants.tripadvisor_european_restaurants_raw`
CLUSTER BY geom AS
SELECT * FROM `cartodb-on-gcp-cs-team.paris_restaurants.tripadvisor_european_restaurants_raw`;

-- Paris restaurants with game attributes, H3 res 10
CREATE OR REPLACE TABLE `cartodb-on-gcp-cs-team.paris_restaurants.restaurants`
CLUSTER BY h3 AS
WITH p AS (
  SELECT *,
    LOWER(CONCAT(IFNULL(cuisines, ''), ',', IFNULL(top_tags, ''))) AS tags_lc,
    LOWER(restaurant_name) AS name_lc
  FROM `cartodb-on-gcp-cs-team.paris_restaurants.tripadvisor_european_restaurants_raw`
  WHERE city = 'Paris' AND country = 'France' AND geom IS NOT NULL AND avg_rating IS NOT NULL
)
SELECT
  restaurant_link AS restaurant_id,
  restaurant_name AS name,
  address,
  geom,
  `carto-un`.carto.H3_FROMGEOGPOINT(geom, 10) AS h3,
  cuisines,
  top_tags,
  price_level,
  price_range,
  CASE price_level WHEN '€' THEN 1 WHEN '€€-€€€' THEN 2 WHEN '€€€€' THEN 3 END AS price_tier,
  CAST(avg_rating AS FLOAT64) AS rating,
  CAST(total_reviews_count AS INT64) AS reviews,
  awards,
  CASE
    WHEN awards LIKE '%Three Michelin Stars%' THEN 3
    WHEN awards LIKE '%Two Michelin Stars%' THEN 2
    WHEN awards LIKE '%One Michelin Star%' THEN 1
    ELSE 0 END AS michelin_stars,
  awards LIKE '%Bib Gourmand%' AS bib_gourmand,
  awards LIKE '%Michelin%' AS michelin_listed,
  awards LIKE '%Travellers\' Choice%' AS travellers_choice,
  vegetarian_friendly = 'Y' AS vegetarian,
  vegan_options = 'Y' AS vegan,
  gluten_free = 'Y' AS gluten_free,
  meals,
  original_open_hours AS open_hours,
  ARRAY(SELECT g FROM UNNEST([
    IF(REGEXP_CONTAINS(name_lc, r'bistro|brasserie|bouillon'), 'bistro', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'\bfrench\b'), 'french', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'italian|pizza'), 'italian', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'japanese|sushi'), 'japanese', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'chinese|vietnamese|thai|korean|cambodian|taiwanese|\basian\b'), 'asian', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'middle eastern|lebanese|moroccan|turkish|greek|israeli|persian|mediterranean'), 'mediterranean', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'fast food|street food|deli|diner|american|burger'), 'quick', NULL),
    IF(REGEXP_CONTAINS(tags_lc, r'\bbar\b|wine bar|\bpub\b|gastropub|brew pub|dining bars'), 'bar', NULL)
  ]) AS g WHERE g IS NOT NULL) AS cuisine_groups
FROM p;
