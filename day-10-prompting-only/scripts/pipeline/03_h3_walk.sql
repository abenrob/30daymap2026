-- Smallest walk minute per H3 res-10 cell, per hotel (the "H3 isochrone")
CREATE OR REPLACE TABLE `cartodb-on-gcp-cs-team.paris_restaurants.hotel_h3_walk`
CLUSTER BY hotel_id, h3 AS
SELECT hotel_id, h3, MIN(minutes) AS minutes
FROM `cartodb-on-gcp-cs-team.paris_restaurants.isolines`,
UNNEST(`carto-un`.carto.H3_POLYFILL(geom, 10)) AS h3
GROUP BY hotel_id, h3;
