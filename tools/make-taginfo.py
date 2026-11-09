#!/usr/bin/python3
"""Generate taginfo.json for this style

The tag -> symbol mapping below mirrors the rules in inc/*.xml and needs to
be kept in sync with them by hand; the seamark:notice:category values are
read from inc/notice.xml directly. Icons are the PNGs created by
tools/svg2png-icons.py (make icons), which are checked to exist, as are all
symbol files referenced by the style.

usage: make-taginfo.py   (writes taginfo.json in the repo root)"""
import datetime
import glob
import json
import os
import re
import sys

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

RAW = 'https://raw.githubusercontent.com/hholzgra/mapnik-seamap-overlay/main/'
N = ['node']
NA = ['node', 'area']
A = ['area']
W = ['way']

tags = []


def icon(sym):
    if sym is None:
        return None
    png = 'taginfo/icons/' + sym + '.png'
    if not os.path.exists(png):
        sys.exit('%s not found, run "make icons" first' % png)
    return RAW + png


def add(key, value, objs, desc, sym=None):
    t = {'key': key}
    if value is not None:
        t['value'] = value
    t['object_types'] = objs
    t['description'] = desc
    if sym:
        t['icon_url'] = icon(sym)
    tags.append(t)


# all symbols referenced by the style must exist
missing = sorted({f for x in glob.glob('inc/*.xml')
                  for f in re.findall(r'file=["\'](symbols/[^"\']+)', open(x).read())
                  if not os.path.exists(f)})
if missing:
    sys.exit('symbol files referenced in inc/*.xml not found: ' + ', '.join(missing))

# --- lights
add('seamark:light:colour', None, N,
    'Any node with seamark:light:* tags gets a light flare in the light\'s colour '
    '(also numbered seamark:light:N:* sector tags)', 'light/light')
for k, d in (('character', 'Light characteristic, part of the light label'),
             ('group', 'Light group, part of the light label'),
             ('period', 'Light period, part of the light label'),
             ('range', 'Light range, part of the light label and the sector arc radius'),
             ('height', 'Light height, part of the light label'),
             ('category', 'Light category, "directional" lights are labelled differently'),
             ('sector_start', 'Start bearing of a light sector arc'),
             ('sector_end', 'End bearing of a light sector arc')):
    add('seamark:light:' + k, None, N, d + ' (also numbered seamark:light:N:%s)' % k)
add('seamark:type', 'light_major', N, 'Major light', 'light/major')
add('seamark:type', 'light_minor', N, 'Minor light', 'light/minor')
add('seamark:name', None, NA, 'Label for major lights, anchorages and hulks')

# --- harbour
add('seamark:type', 'harbour', NA, 'Harbour', 'harbour/harbour')
add('water', 'harbour', NA, 'Harbour', 'harbour/harbour')
for v in ('fishing', 'marina', 'marina_no_facilities'):
    add('seamark:harbour:category', v, NA, 'Harbour category %s' % v, 'harbour/' + v)

# --- anchorage, restricted areas
add('seamark:type', 'anchorage', NA, 'Anchorage, areas get a dashed anchor border',
    'anchorage/anchorage')
add('seamark:type', 'restricted_area', A,
    'Restricted area border (not for boundary=protected_area)', 'anchorage/restricted')
add('seamark:type', 'dumping_ground', A,
    'Dumping ground, rendered like a restricted area', 'anchorage/restricted')

# --- rocks and wrecks
add('seamark:type', 'rock', N, 'Rock', 'rock/rock')
add('seamark:rock:water_level', 'awash', N, 'Rock awash', 'rock/awash')
add('seamark:rock:water_level', 'covers', N, 'Rock that covers and uncovers', 'rock/covers')

add('seamark:type', 'wreck', N, 'Wreck', 'wreck/dangerous')
for v, s in (('dangerous', 'dangerous'), ('mast_showing', 'dangerous'),
             ('non-dangerous', 'non_dangerous'), ('distributed_remains', 'non_dangerous'),
             ('hull_showing', 'showing')):
    add('seamark:wreck:category', v, N, 'Wreck category %s' % v, 'wreck/' + s)

# --- buoys and beacons: shape key depends on seamark:type
buoy_shapes = (('conical', 'buoy/cone/outer'), ('can', 'buoy/can/outer'),
               ('spherical', 'buoy/sphere/outer'), ('pillar', 'buoy/pillar/outer'),
               ('spar', 'buoy/spar/outer'), ('barrel', 'buoy/barrel/outer'),
               ('super-buoy', 'buoy/installation/outer'))
for t in ('cardinal', 'installation', 'isolated_danger', 'lateral', 'safe_water',
          'special_purpose'):
    typ = 'buoy_' + t
    add('seamark:type', typ, N, 'Buoy, shape only (no colours or top marks yet)',
        'buoy/spar/outer')
    for v, s in buoy_shapes:
        add('seamark:%s:shape' % typ, v, N, 'Buoy shape %s' % v, s)

beacon_shapes = (('pile', 'beacon/pile/outer'), ('lattice', 'beacon/pile/outer'),
                 ('buoyant', 'beacon/pile/outer'), ('perch', 'beacon/stake/stake'),
                 ('pole', 'beacon/stake/stake'), ('post', 'beacon/stake/stake'),
                 ('stake', 'beacon/stake/stake'), ('tower', 'beacon/tower/tower'),
                 ('cairn', 'beacon/tower/tower'))
for t in ('cardinal', 'isolated_danger', 'lateral', 'safe_water', 'special_purpose'):
    typ = 'beacon_' + t
    add('seamark:type', typ, N, 'Beacon, shape only (no colours or top marks yet)',
        'beacon/pile/outer')
    for v, s in beacon_shapes:
        add('seamark:%s:shape' % typ, v, N, 'Beacon shape %s' % v, s)

# --- navigation lines
add('seamark:type', 'navigation_line', W, 'Navigation line, dashed')
add('seamark:navigation_line:orientation', None, W, 'Navigation line label (degrees)')

# --- rescue stations, landmarks, radio, fog signals
add('seamark:type', 'rescue_station', NA, 'Rescue station', 'rescue/station')

add('seamark:type', 'landmark', N,
    'Landmark; without category it is shown as a major light like on OpenSeaMap',
    'light/major')
add('seamark:landmark:category', 'mast', N, 'Mast', 'landmark/mast')
add('seamark:landmark:category', 'chimney', N, 'Chimney', 'landmark/chimney')
add('seamark:landmark:function', 'light', N,
    'Landmark without category but with light function is shown as major light',
    'light/major')

add('seamark:type', 'radio_station', N, 'Radio station with range circle',
    'radio_station/station')
add('seamark:radio_station:category', None, N,
    'Radio station label (AIS, RC, RD, DGPS ...)')

add('seamark:type', 'fog_signal', N, 'Fog signal', 'fog_signal/fog_signal')
add('seamark:fog_signal:category', None, N,
    'Nodes with a fog signal category get a fog signal symbol and label',
    'fog_signal/fog_signal')
add('seamark:fog_signal:group', None, N, 'Fog signal group, part of the fog signal label')
add('seamark:fog_signal:period', None, N, 'Fog signal period, part of the fog signal label')

# --- moorings, hulks
add('seamark:type', 'mooring', N, 'Mooring, rendered depending on category')
for v, s in (('dolphin', 'dolphin'), ('deviated_dolphin', 'deviated_dolphin'),
             ('buoy', 'mooring'), ('pile', 'pile'), ('post', 'post'), ('bollard', 'post')):
    add('seamark:mooring:category', v, N, 'Mooring %s' % v.replace('_', ' '), 'mooring/' + s)

add('seamark:type', 'hulk', A, 'Hulk, yellow area with name label')

# --- notices: value -> symbol pairs straight from the style
src = open('inc/notice.xml').read()
seen = set()
add('seamark:type', 'notice', N, 'Notice mark (CEVNI waterway sign), rendered by category')
for v, f in re.findall(r"\[category\] = '([^']+)'</Filter>\s*"
                       r"<MarkersSymbolizer[^>]*file=\"symbols/([^\"]+)\.svg\"", src):
    if v in seen:
        continue
    seen.add(v)
    group = f.split('/')[1]
    add('seamark:notice:category', v, N,
        '%s notice: %s' % (group.capitalize(), v.replace('_', ' ')), f)

# --- waterway gauges, bridges, cranes
add('seamark:type', 'waterway_gauge', N, 'Waterway gauge', 'waterway_gauge/waterway_gauge')
add('seamark:type', 'bridge', N, 'Bridge, shown only with a clearance height')
add('seamark:bridge:clearance_height', None, N, 'Bridge clearance height shield',
    'bridge/clearance_height')
add('seamark:type', 'crane', ['node', 'way', 'area'], 'Crane', 'crane/crane')
add('seamark:crane:category', 'container', ['node', 'way', 'area'], 'Container crane',
    'crane/container_crane')

# --- small craft facilities
add('seamark:type', 'small_craft_facility', N,
    'Small craft facility, rendered depending on category')
for v in ('visitor_berth', 'nautical_club', 'boat_hoist', 'boatyard', 'chandler',
          'fuel_station', 'showers', 'launderette', 'toilets', 'pump_out', 'slipway',
          'visitor_mooring'):
    add('seamark:small_craft_facility:category', v, N, v.replace('_', ' ').capitalize(),
        'small_craft_facility/' + v)

doc = {
    'data_format': 1,
    'data_url': RAW + 'taginfo.json',
    'data_updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
    'project': {
        'name': 'MapOSMatic seamap overlay',
        'description': 'Mapnik overlay style rendering sea marks and lights similar to '
                       'OpenSeaMap, for printable maps with MapOSMatic.',
        'project_url': 'https://github.com/hholzgra/mapnik-seamap-overlay',
        'icon_url': icon('light/major'),
        'contact_name': 'Hartmut Holzgraefe',
        'contact_email': 'hartmut.holzgraefe@gmail.com',
    },
    'tags': tags,
}

# no duplicate key/value pairs
kv = [(t['key'], t.get('value')) for t in tags]
dups = {x for x in kv if kv.count(x) > 1}
if dups:
    sys.exit('duplicate taginfo entries: %s' % dups)

with open('taginfo.json', 'w') as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('taginfo.json: %d tags' % len(tags))
