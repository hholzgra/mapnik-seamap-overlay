-- the direction of the longest axis of a polygon
-- to e.g. rotate text on a ship hulk 
CREATE FUNCTION label_angle(g geometry) RETURNS double precision AS $$
  SELECT a - 180 * floor((a + 90) / 180)
  FROM (SELECT ST_ExteriorRing(ST_OrientedEnvelope(g)) AS r) e,
  LATERAL (SELECT 90 - degrees(ST_Azimuth(ST_PointN(r, 1), ST_PointN(r, 2)))
                  - CASE WHEN ST_Distance(ST_PointN(r, 1), ST_PointN(r, 2))
                            < ST_Distance(ST_PointN(r, 2), ST_PointN(r, 3))
                         THEN 90 ELSE 0 END AS a) x
$$ LANGUAGE sql IMMUTABLE; 
