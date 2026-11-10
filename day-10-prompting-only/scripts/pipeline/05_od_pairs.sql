-- Every hotel x restaurant pair inside the 15 min H3 walk isochrone
CREATE OR REPLACE TABLE `cartodb-on-gcp-cs-team.paris_restaurants.od_pairs`
CLUSTER BY hotel_id AS
SELECT h.hotel_id, r.restaurant_id, w.minutes AS h3_minutes,
       h.geom AS origin, r.geom AS destination
FROM `cartodb-on-gcp-cs-team.paris_restaurants.hotel_h3_walk` w
JOIN `cartodb-on-gcp-cs-team.paris_restaurants.restaurants` r ON r.h3 = w.h3
JOIN `cartodb-on-gcp-cs-team.paris_restaurants.hotels` h ON h.hotel_id = w.hotel_id
WHERE w.minutes <= 15;
