# seamap-overlay

An overlay that tries to render navigational marks etc. in a way similar
to OpenSeaMap, to be used with MapOSMatic to create printable maps.

We can't use the original OpenSeaMap renderer(s) for this as the
OpenSeaMap project chose to implement their own rendering from scratch,
supporting bitmap (and soon vector) tile output only.

Now that preliminary support for circle sector arcs for Mapnik exists
in the form of a pull request (for both Mapnik itself and its Python
Bindings) we can finally render navigation lights the same way as on
OpenSeaMap and try to mimic their style. 

Won't be a perfect 1:1 copy, but we should get close enough for it to
get  useful map prints out of it.

## Things rendered

So far only renders sea lights and their visibility sector arcs,
plus a few selected other symbols:

* harbours and marinas
* anchorage areas
* restricted areas
* rocks and wrecks
* some first buoys: lateral and special purpose

## Requirements

This style requires Mapnik built with the experimental ArcSymbolizer
support (AGG, Cairo or SVG backend).

## Database setup

The Mapnik style needs some custom stored SQL functions which
need to be installed on top of an "all tags" openstreetmap-carto
database impoort, thse can be insalled using:

```
psql -d gis -f sql-functions/seamark_lights.sql
```

In the future we'll probably create our own osm2pgsql flex tables
and have much of the logic currently present in those SQL functions
and the <Layer> SQL queries moved to import time Lua code, improving
render runtime performance.

## Symbol assets

The symbol asset SVG files are loosely based on those found in the
old OpenSeaMap C++ renderer project.
