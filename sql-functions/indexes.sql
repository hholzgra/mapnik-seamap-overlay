CREATE INDEX idx_seamark_type_point ON planet_osm_point ((tags -> 'seamark:type'));
CREATE INDEX idx_seamark_type_line ON planet_osm_line ((tags -> 'seamark:type'));
CREATE INDEX idx_seamark_type_polygon ON planet_osm_polygon ((tags -> 'seamark:type'));

