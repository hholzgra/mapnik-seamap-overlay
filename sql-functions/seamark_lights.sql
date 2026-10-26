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
-- sector, ready to be fed to the ArcSymbolizer. range is the sector light's
-- nominal range in nautical miles, NULL if not tagged.
-- (DROP needed as CREATE OR REPLACE can't change the result columns)
DROP FUNCTION IF EXISTS seamark_light_sectors(hstore);
CREATE FUNCTION seamark_light_sectors(tags hstore)
RETURNS TABLE(colour text, sector_start float, sector_end float, label text, range float) AS $$
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
      range  := seamark_safe_float(tags -> (k_prefix || 'range'));
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
      range  := seamark_safe_float(tags -> 'seamark:light:range');
      RETURN NEXT;
    END IF;
  END IF;

  RETURN;
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Format a number like Java's DecimalFormat("#.#"): at most one decimal
-- place, no trailing ".0" (17 -> "17", 2.5 -> "2.5")
CREATE OR REPLACE FUNCTION seamark_format_number(x float) RETURNS TEXT AS $$
  SELECT rtrim(rtrim(round(x::numeric, 1)::text, '0'), '.');
$$ LANGUAGE sql IMMUTABLE;

-- Map a seamark:light:colour value to its chart abbreviation letter(s)
CREATE OR REPLACE FUNCTION seamark_light_colour_letter(colour text) RETURNS TEXT AS $$
  SELECT CASE lower(colour)
    WHEN 'white'  THEN 'W'
    WHEN 'red'    THEN 'R'
    WHEN 'green'  THEN 'G'
    WHEN 'blue'   THEN 'Bu'
    WHEN 'yellow' THEN 'Y'
    WHEN 'amber'  THEN 'Am'
    WHEN 'violet' THEN 'Vi'
    WHEN 'orange' THEN 'Or'
    ELSE ''
  END;
$$ LANGUAGE sql IMMUTABLE;

-- Combined characteristics label for a multi-sector light, e.g.
-- "Iso.WGR.4s17m11-10M", following the OpenSeaMap tile renderer (JOSM
-- SeaChart, lights() in render/Signals.java):
--
-- * all lights of the point (indexed ones plus an unindexed one, if any)
--   that have a character are grouped by (directional, character, group,
--   period, height); each group becomes one label line, groups with more
--   members first, ties in order of first appearance
-- * within a group every colour gets the maximum range of its sectors;
--   colours are listed by range descending, ties in sector order
-- * the range part shows the first (highest) colour range, followed by
--   "/<second>" for two colours or "-<last>" for three or more
--
-- Only the first value of multi-valued character/colour tags is used, and
-- "Al.*" alternating characters are reduced to their base character, as
-- SeaChart does. Lines are separated by newlines.
CREATE OR REPLACE FUNCTION seamark_light_sector_label(tags hstore) RETURNS TEXT AS $$
  WITH prefixes AS (
    SELECT DISTINCT
           coalesce(substring(key FROM '^seamark:light:([0-9]+):')::int, 0) AS i
      FROM skeys(tags) AS key
     WHERE key LIKE 'seamark:light:%'
  ), lights AS (
    SELECT i,
           coalesce('directional' = ANY (string_to_array(tags -> (p || 'category'), ';')),
                    false) AS dir,
           seamark_light_character_abbr(split_part(tags -> (p || 'character'), ';', 1)) AS chr,
           coalesce(tags -> (p || 'group'), '') AS grp,
           coalesce(seamark_safe_float(tags -> (p || 'period')), 0) AS per,
           coalesce(seamark_safe_float(tags -> (p || 'range')), 0) AS rng,
           coalesce(seamark_safe_float(tags -> (p || 'height')), 0) AS hgt,
           split_part(tags -> (p || 'colour'), ';', 1) AS col
      FROM (SELECT i,
                   CASE WHEN i = 0 THEN 'seamark:light:'
                        ELSE 'seamark:light:' || i || ':' END AS p
              FROM prefixes) pr
     WHERE tags ? (p || 'character')
  ), sectors AS (
    SELECT i, dir,
           CASE chr
             WHEN 'Al'     THEN 'F'
             WHEN 'Al.Oc'  THEN 'Oc'
             WHEN 'Al.LFl' THEN 'LFl'
             WHEN 'Al.Fl'  THEN 'Fl'
             WHEN 'Al.FFl' THEN 'FFl'
             ELSE chr
           END AS chr,
           grp, per, rng, hgt, col
      FROM lights
  ), colours AS (
    SELECT dir, chr, grp, per, hgt, col,
           max(rng) AS rng, min(i) AS first_i, count(*) AS n
      FROM sectors
     GROUP BY dir, chr, grp, per, hgt, col
  ), groups AS (
    SELECT dir, chr, grp, per, hgt,
           sum(n) AS n, min(first_i) AS first_i,
           string_agg(seamark_light_colour_letter(col), '' ORDER BY rng DESC, first_i) AS letters,
           array_agg(rng ORDER BY rng DESC, first_i) AS rngs
      FROM colours
     GROUP BY dir, chr, grp, per, hgt
  )
  SELECT string_agg(
           CASE WHEN dir THEN 'Dir' ELSE '' END
           || chr
           || CASE WHEN grp <> '' THEN '(' || grp || ')' ELSE '.' END
           || letters
           || CASE WHEN per > 0 OR hgt > 0 OR rngs[1] > 0 THEN '.' ELSE '' END
           || CASE WHEN per > 0 THEN seamark_format_number(per) || 's' ELSE '' END
           || CASE WHEN hgt > 0 THEN seamark_format_number(hgt) || 'm' ELSE '' END
           || CASE WHEN rngs[1] > 0 THEN
                seamark_format_number(rngs[1])
                || CASE
                     WHEN cardinality(rngs) = 2 THEN '/' || seamark_format_number(rngs[2])
                     WHEN cardinality(rngs) > 2 THEN '-' || seamark_format_number(rngs[cardinality(rngs)])
                     ELSE ''
                   END
                || 'M'
              ELSE '' END,
           E'\n' ORDER BY n DESC, first_i)
    FROM groups;
$$ LANGUAGE sql IMMUTABLE;

-- Characteristics label for a single (unindexed) light, e.g. "Fl.5s82m28M"
-- or "Q(6)+LFl.15s", following the OpenSeaMap tile renderer (JOSM SeaChart,
-- single light branch of lights() in render/Signals.java). The colour is
-- left out for a plain white light.
CREATE OR REPLACE FUNCTION seamark_light_single_label(tags hstore) RETURNS TEXT AS $$
DECLARE
  p    text := 'seamark:light:';
  cats text[] := coalesce(string_to_array(tags -> 'seamark:light:category', ';'), '{}');
  cols text[] := string_to_array(tags -> 'seamark:light:colour', ';');
  chr  text := seamark_light_character_abbr(split_part(tags -> 'seamark:light:character', ';', 1));
  grp  text := tags -> 'seamark:light:group';
  col  text;
  str  text := '';
BEGIN
  IF 'aero' = ANY (cats) OR 'air_obstruction' = ANY (cats) THEN
    str := 'Aero';
  ELSIF 'directional' = ANY (cats) THEN
    str := 'Dir';
  END IF;

  str := str || coalesce(tags -> (p || 'multiple'), '');

  IF chr IS NOT NULL THEN
    IF grp IS NOT NULL THEN
      str := str || CASE chr
                      WHEN 'Q+LFl'  THEN 'Q(' || grp || ')+LFl'
                      WHEN 'VQ+LFl' THEN 'VQ(' || grp || ')+LFl'
                      WHEN 'UQ+LFl' THEN 'UQ(' || grp || ')+LFl'
                      ELSE chr || '(' || grp || ')'
                    END;
    ELSE
      str := str || chr;
    END IF;
  END IF;

  IF cols IS NOT NULL AND NOT (cardinality(cols) = 1 AND lower(cols[1]) = 'white') THEN
    IF str <> '' AND right(str, 1) <> ')' THEN
      str := str || '.';
    END IF;
    FOREACH col IN ARRAY cols LOOP
      str := str || seamark_light_colour_letter(col);
    END LOOP;
  END IF;

  IF 'vertical' = ANY (cats) THEN str := str || '(vert)'; END IF;
  IF 'horizontal' = ANY (cats) THEN str := str || '(hor)'; END IF;

  -- SeaChart checks maximum_range here but prints range below
  IF str <> '' AND right(str, 1) <> ')'
     AND (tags ? (p || 'period') OR tags ? (p || 'height') OR tags ? (p || 'maximum_range')) THEN
    str := str || '.';
  END IF;

  IF tags ? (p || 'period') THEN
    str := str || coalesce(seamark_format_number(seamark_safe_float(tags -> (p || 'period'))), '') || 's';
  END IF;
  IF tags ? (p || 'height') THEN
    str := str || coalesce(seamark_format_number(seamark_safe_float(tags -> (p || 'height'))), '') || 'm';
  END IF;
  IF tags ? (p || 'range') THEN
    str := str || coalesce(seamark_format_number(seamark_safe_float(tags -> (p || 'range'))), '') || 'M';
  END IF;

  IF 'front' = ANY (cats) THEN str := str || '(Front)'; END IF;
  IF 'rear'  = ANY (cats) THEN str := str || '(Rear)';  END IF;
  IF 'upper' = ANY (cats) THEN str := str || '(Upper)'; END IF;
  IF 'lower' = ANY (cats) THEN str := str || '(Lower)'; END IF;

  RETURN nullif(str, '');
END
$$ LANGUAGE plpgsql IMMUTABLE;

-- Characteristics label for any light point, choosing the format the way
-- SeaChart does: the grouped multi-sector label as soon as indexed lights
-- ("seamark:light:1:*") exist, the single light label otherwise.
CREATE OR REPLACE FUNCTION seamark_light_characteristics(tags hstore) RETURNS TEXT AS $$
  SELECT CASE
    WHEN EXISTS (SELECT 1 FROM skeys(tags) AS key WHERE key LIKE 'seamark:light:1:%')
      THEN seamark_light_sector_label(tags)
    ELSE seamark_light_single_label(tags)
  END;
$$ LANGUAGE sql IMMUTABLE;
