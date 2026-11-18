CREATE OR REPLACE FUNCTION distance_mark_label(distance text, unit text) RETURNS TEXT AS $$
DECLARE
  label text;
BEGIN
  label := CASE unit
    WHEN 'kilometres'     THEN 'km'
    WHEN 'kilometer'      THEN 'km'
    WHEN 'mectometres'    THEN 'hm'
    WHEN 'metres'         THEN 'm'
    WHEN 'statute_miles'  THEN 'mi'
    WHEN 'nautical_miles' THEN 'nm'
    ELSE COALESCE(unit, '')
  END;

  IF label <> '' THEN
    label := CONCAT(label, ' ');
  END IF;

  RETURN CONCAT(label, distance);
END
$$ LANGUAGE plpgsql IMMUTABLE;
