CREATE OR REPLACE FUNCTION signal_station_traffic_label(category text) RETURNS TEXT AS $$
DECLARE
  label text;
BEGIN
  label := CASE category
    WHEN 'port_control'          THEN 'PortControl'
    WHEN 'port_entry_departure'  THEN 'Traffic'
    WHEN 'traffic_control_light' THEN 'Traffic'
    WHEN 'ipt'                   THEN 'INT'
    WHEN 'lock'                  THEN 'Lock'
    WHEN 'bridge_passage'        THEN 'Bridge'
    ELSE ''
  END;

  IF label <> '' THEN
    RETURN CONCAT('SS(', label, ')');
  ELSE
    RETURN 'SS';
  END IF;

END
$$ LANGUAGE plpgsql IMMUTABLE;
