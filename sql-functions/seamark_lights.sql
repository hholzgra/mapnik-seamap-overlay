-- Helper functions for rendering seamark lights (seamark:light:* tags)
--
-- OSM's seamark tagging scheme allows a single point to carry either one
-- unindexed light ("seamark:light:colour", "seamark:light:sector_start", ...)
-- or several indexed lights/sectors ("seamark:light:1:colour",
-- "seamark:light:2:colour", ...). These helpers normalize both cases.

-- Does this point carry any light information at all?
CREATE OR REPLACE FUNCTION seamark_has_light(tags hstore) RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM each(tags) e WHERE e.key LIKE 'seamark:light:%'
  );
$$ LANGUAGE sql IMMUTABLE;

-- Does this point carry at least one light sector (as opposed to a plain
-- omnidirectional light)?
CREATE OR REPLACE FUNCTION seamark_has_light_sector(tags hstore) RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM each(tags) e WHERE e.key LIKE 'seamark:light:%sector_start'
  );
$$ LANGUAGE sql IMMUTABLE;

-- Map a seamark:light:colour value to a display colour
CREATE OR REPLACE FUNCTION seamark_light_colour_hex(colour text) RETURNS TEXT AS $$
BEGIN
  RETURN CASE lower(coalesce(colour, 'magenta'))
    WHEN 'white'  THEN '#ffff00'
    ELSE colour
  END;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Display colour for the light flare symbol of a point, following the
-- OpenSeaMap renderer (renderFlare() in searender/render.c): if all
-- (indexed and unindexed) lights share one single colour, use that colour;
-- if they differ, or any light is multi-coloured (e.g. "white;red"
-- alternating), use magenta as the generic chart light colour.
-- Floodlights are ignored, as OpenSeaMap draws a separate symbol for them.
CREATE OR REPLACE FUNCTION seamark_light_flare_colour(tags hstore) RETURNS TEXT AS $$
  WITH lights AS (
    SELECT lower(trim(e.value)) AS colour,
           tags -> regexp_replace(e.key, 'colour$', 'category') AS category
      FROM each(tags) e
     WHERE e.key ~ '^seamark:light:([0-9]+:)?colour$'
  )
  SELECT CASE
    WHEN count(*) = 0 THEN seamark_light_colour_hex(NULL)
    WHEN count(DISTINCT colour) > 1 OR bool_or(colour LIKE '%;%') THEN 'magenta'
    ELSE seamark_light_colour_hex(min(colour))
  END
  FROM lights
  WHERE coalesce('floodlight' <> ALL (string_to_array(category, ';')), true);
$$ LANGUAGE sql IMMUTABLE;

-- Map a seamark:light:character value to its standard IHO abbreviation
CREATE OR REPLACE FUNCTION seamark_light_character_abbr(light_character text) RETURNS TEXT AS $$
BEGIN
  RETURN CASE light_character
    WHEN 'fixed'                             THEN 'F'
    WHEN 'flashing'                          THEN 'Fl'
    WHEN 'long-flashing'                     THEN 'LFl'
    WHEN 'quick-flashing'                    THEN 'Q'
    WHEN 'very_quick-flashing'               THEN 'VQ'
    WHEN 'ultra_quick-flashing'               THEN 'UQ'
    WHEN 'interrupted_quick-flashing'        THEN 'IQ'
    WHEN 'interrupted_very_quick-flashing'   THEN 'IVQ'
    WHEN 'interrupted_ultra_quick-flashing'  THEN 'IUQ'
    WHEN 'isophased'                         THEN 'Iso'
    WHEN 'occulting'                         THEN 'Occ'
    WHEN 'group-flashing'                    THEN 'Gp Fl'
    WHEN 'group-occulting'                   THEN 'Gp Occ'
    WHEN 'composite_group-flashing'          THEN 'FFl'
    WHEN 'morse'                             THEN 'Mo'
    WHEN 'fixed_and_flashing'                THEN 'F Fl'
    ELSE light_character
  END;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Build a short light characteristic label, e.g. "Fl(3).15s"
CREATE OR REPLACE FUNCTION seamark_light_label(light_character text, group_ text, period text) RETURNS TEXT AS $$
DECLARE
  label text;
BEGIN
  IF light_character IS NULL THEN
    RETURN NULL;
  END IF;

  label := seamark_light_character_abbr(light_character);

  IF group_ IS NOT NULL AND group_ <> '1' THEN
    label := label || '(' || group_ || ')';
  END IF;

  IF period IS NOT NULL THEN
    label := label || '.' || period || 's';
  END IF;

  RETURN label;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Cast to float, returning NULL instead of raising on malformed input
CREATE OR REPLACE FUNCTION seamark_safe_float(s text) RETURNS float AS $$
BEGIN
  RETURN s::float;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- seamark:light:sector_start/sector_end are bearings "from seaward", i.e.
-- the compass bearing a mariner out at sea would measure FROM their own
-- position TO the light (per Admiralty List of Lights convention). The
-- ArcSymbolizer instead needs the bearing FROM the light TO the sea area
-- it illuminates, which is the reciprocal bearing -- 180 degrees apart.
CREATE OR REPLACE FUNCTION seamark_sector_bearing(bearing float) RETURNS float AS $$
BEGIN
  IF bearing IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN (bearing + 180) - 360 * floor((bearing + 180) / 360);
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Unnest the (possibly indexed) light sectors of a point into one row per
-- sector, ready to be fed to the ArcSymbolizer.
CREATE OR REPLACE FUNCTION seamark_light_sectors(tags hstore)
RETURNS TABLE(colour text, sector_start float, sector_end float, label text) AS $$
DECLARE
  i int;
  k_prefix text;
  v_start text;
  v_end text;
  found boolean := false;
BEGIN
  FOR i IN 1..12 LOOP
    k_prefix := 'seamark:light:' || i || ':';

    EXIT WHEN NOT (tags ? (k_prefix || 'colour')
                   OR tags ? (k_prefix || 'sector_start')
                   OR tags ? (k_prefix || 'sector_end'));

    v_start := tags -> (k_prefix || 'sector_start');
    v_end   := tags -> (k_prefix || 'sector_end');

    sector_start := seamark_sector_bearing(seamark_safe_float(v_start));
    sector_end   := seamark_sector_bearing(seamark_safe_float(v_end));

    IF sector_start IS NOT NULL AND sector_end IS NOT NULL THEN
      found  := true;
      colour := seamark_light_colour_hex(tags -> (k_prefix || 'colour'));
      label  := seamark_light_label(tags -> (k_prefix || 'character'),
                                     tags -> (k_prefix || 'group'),
                                     tags -> (k_prefix || 'period'));
      RETURN NEXT;
    END IF;
  END LOOP;

  IF NOT found THEN
    v_start := tags -> 'seamark:light:sector_start';
    v_end   := tags -> 'seamark:light:sector_end';
    sector_start := seamark_sector_bearing(seamark_safe_float(v_start));
    sector_end   := seamark_sector_bearing(seamark_safe_float(v_end));

    IF sector_start IS NOT NULL AND sector_end IS NOT NULL THEN
      colour := seamark_light_colour_hex(tags -> 'seamark:light:colour');
      label  := seamark_light_label(tags -> 'seamark:light:character',
                                     tags -> 'seamark:light:group',
                                     tags -> 'seamark:light:period');
      RETURN NEXT;
    END IF;
  END IF;

  RETURN;
END
$$ LANGUAGE plpgsql IMMUTABLE;
