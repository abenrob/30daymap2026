// Every runtime read is a parameterised SQL query against the warehouse through
// CARTO's SQL API. The query texts are constant so the public token can grant
// exactly these queries and nothing else.
import { query } from '@carto/api-client';

const DS = 'cartodb-on-gcp-cs-team.paris_restaurants';

const cfg = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL as string,
  accessToken: import.meta.env.VITE_API_ACCESS_TOKEN as string,
  connectionName: import.meta.env.VITE_CONNECTION_NAME as string,
};

// The five queries the app runs. Each text is granted verbatim on the public token, so
// changing one means adding a new grant (see scripts/pipeline/README.md).
export const SQL = {
  // The eight starting hotels, west to east
  hotels: `SELECT hotel_id, name, address, area, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM \`${DS}.hotels\` ORDER BY ST_X(geom)`,

  // The hotel's H3 walk isochrone: res-10 cells with the minute each is reached
  h3: `SELECT h3, minutes FROM \`${DS}.hotel_h3_walk\` WHERE hotel_id = @hotel AND minutes <= 15`,

  // Restaurants inside the walk, joined on the H3 cell, filtered by every answer, with the
  // precomputed route's distance and duration. LIMIT is above the largest possible result.
  search: `SELECT r.restaurant_id, r.name, r.address, ST_X(r.geom) AS lon, ST_Y(r.geom) AS lat, w.minutes, r.cuisines, r.price_level, r.price_range, r.rating, r.reviews, r.michelin_stars, r.bib_gourmand, r.michelin_listed, r.travellers_choice, r.vegetarian, r.vegan, r.gluten_free, r.open_hours, CAST(JSON_VALUE(rt.carto_routing_metadata, '$.routes[0].summary.lengthInMeters') AS INT64) AS distance_m, CAST(JSON_VALUE(rt.carto_routing_metadata, '$.routes[0].summary.travelTimeInSeconds') AS INT64) AS duration_s FROM \`${DS}.hotel_h3_walk\` w JOIN \`${DS}.restaurants\` r ON r.h3 = w.h3 LEFT JOIN \`${DS}.routes\` rt ON rt.hotel_id = w.hotel_id AND rt.restaurant_id = r.restaurant_id WHERE w.hotel_id = @hotel AND w.minutes <= @maxmin AND (@cuisine = 'any' OR @cuisine IN UNNEST(r.cuisine_groups)) AND (@price = 0 OR r.price_tier = @price) AND (@diet = 'none' OR (@diet = 'vegetarian' AND r.vegetarian) OR (@diet = 'vegan' AND r.vegan) OR (@diet = 'gluten_free' AND r.gluten_free)) AND (@accolade = 'any' OR (@accolade = 'stars' AND r.michelin_stars > 0) OR (@accolade = 'michelin' AND r.michelin_listed) OR (@accolade = 'travellers' AND r.travellers_choice)) ORDER BY w.minutes, r.rating DESC, r.reviews DESC LIMIT 2500`,

  // For "slim pickings": how many places each single relaxation would give
  relax: `WITH m AS (SELECT w.minutes, (@cuisine = 'any' OR @cuisine IN UNNEST(r.cuisine_groups)) AS c, (@price = 0 OR r.price_tier = @price) AS p, (@diet = 'none' OR (@diet = 'vegetarian' AND r.vegetarian) OR (@diet = 'vegan' AND r.vegan) OR (@diet = 'gluten_free' AND r.gluten_free)) AS d, (@accolade = 'any' OR (@accolade = 'stars' AND r.michelin_stars > 0) OR (@accolade = 'michelin' AND r.michelin_listed) OR (@accolade = 'travellers' AND r.travellers_choice)) AS a FROM \`${DS}.hotel_h3_walk\` w JOIN \`${DS}.restaurants\` r ON r.h3 = w.h3 WHERE w.hotel_id = @hotel) SELECT COUNTIF(c AND p AND d AND a AND minutes <= 15) AS walk, COUNTIF(p AND d AND a AND minutes <= @maxmin) AS cuisine, COUNTIF(c AND d AND a AND minutes <= @maxmin) AS price, COUNTIF(c AND p AND a AND minutes <= @maxmin) AS diet, COUNTIF(c AND p AND d AND minutes <= @maxmin) AS accolade FROM m`,

  // One precomputed route: geometry plus TomTom's instructions, each with the index of
  // the route vertex it applies to (used to sync directions with the animation)
  route: `SELECT ST_ASGEOJSON(geom) AS route, CAST(JSON_VALUE(carto_routing_metadata, '$.routes[0].summary.lengthInMeters') AS INT64) AS distance_m, CAST(JSON_VALUE(carto_routing_metadata, '$.routes[0].summary.travelTimeInSeconds') AS INT64) AS duration_s, TO_JSON_STRING(ARRAY(SELECT AS STRUCT CAST(JSON_VALUE(i, '$.pointIndex') AS INT64) AS i, JSON_VALUE(i, '$.message') AS msg, CAST(JSON_VALUE(i, '$.routeOffsetInMeters') AS INT64) AS m FROM UNNEST(JSON_QUERY_ARRAY(carto_routing_metadata, '$.routes[0].guidance.instructions')) AS i)) AS steps FROM \`${DS}.routes\` WHERE hotel_id = @hotel AND restaurant_id = @rid`,
};

export interface Hotel { hotel_id: string; name: string; address: string; area: string; lon: number; lat: number }
export interface Restaurant {
  restaurant_id: string; name: string; address: string; lon: number; lat: number; minutes: number;
  cuisines: string | null; price_level: string | null; price_range: string | null;
  rating: number; reviews: number | null; michelin_stars: number; bib_gourmand: boolean; michelin_listed: boolean;
  travellers_choice: boolean; vegetarian: boolean; vegan: boolean; gluten_free: boolean;
  open_hours: string | null; distance_m: number | null; duration_s: number | null;
}
export interface Step { i: number; msg: string; m: number }
export interface Filters { hotel: string; maxmin: number; cuisine: string; price: number; diet: string; accolade: string }
export interface Relax { walk: number; cuisine: number; price: number; diet: number; accolade: number }

// Dev only: ?mock replays captured rows so the UI can be tested without a token.
const MOCK = import.meta.env.DEV && new URLSearchParams(location.search).has('mock');
async function mock(sqlQuery: string, p?: Record<string, unknown>): Promise<unknown[]> {
  // glob: an absent fixtures folder (fresh clone) is fine; never bundled in production
  const files = import.meta.env.DEV ? import.meta.glob('../dev-fixtures/fixtures.json') : {};
  const load = Object.values(files)[0];
  if (!load) throw new Error('no dev-fixtures/fixtures.json');
  const fx = ((await load()) as { default: Record<string, unknown[]> }).default;
  if (sqlQuery === SQL.hotels) return fx.hotels;
  if (sqlQuery === SQL.h3) return fx['h3_shangri-la'];
  if (sqlQuery === SQL.relax) return fx.relax;
  if (sqlQuery === SQL.route) return fx.route;
  const rows = fx.search as Restaurant[];
  return rows.filter((r) => r.minutes <= Number(p?.maxmin ?? 15)).slice(0, p?.cuisine === 'bistro' ? 3 : 200);
}

async function run<T>(sqlQuery: string, queryParameters?: Record<string, string | number | boolean>): Promise<T[]> {
  if (MOCK) return (await mock(sqlQuery, queryParameters)) as T[];
  const res = await query({ ...cfg, sqlQuery, queryParameters: queryParameters as never });
  return res.rows as unknown as T[];
}

/** Typed wrappers around the five queries. */
export const db = {
  hotels: () => run<Hotel>(SQL.hotels),
  h3: async (hotel: string) => {
    const rows = await run<{ h3: string; minutes: number }>(SQL.h3, { hotel });
    return new Map(rows.map((r) => [r.h3, Number(r.minutes)]));
  },
  search: (f: Filters) => run<Restaurant>(SQL.search, { ...f } as unknown as Record<string, string | number>),
  relax: async (f: Filters) => (await run<Relax>(SQL.relax, { ...f } as unknown as Record<string, string | number>))[0],
  route: async (hotel: string, rid: string) => {
    const r = (await run<{ route: string; distance_m: number; duration_s: number; steps: string }>(SQL.route, { hotel, rid }))[0];
    if (!r) return null;
    const steps: Step[] = JSON.parse(r.steps || '[]');
    const g = JSON.parse(r.route);
    const coords: [number, number][] = g.type === 'LineString' ? g.coordinates : g.coordinates.flat();
    return { coords, steps, distance_m: Number(r.distance_m), duration_s: Number(r.duration_s) };
  },
};
