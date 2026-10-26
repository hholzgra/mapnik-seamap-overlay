# SeaMap Overlay TODO list

## Short term

* add missing "simple" symbols, mostly thouse not requiring
  any colouring or top marker modifications
* add zoom level restrictions
* improve feature scaling
* ...

## Medium term

* take care of beacon and buoy coloring and top markers
* ...

## Long term

### Use osm2pgsql flex to create separate seamark tables

Right now we are extracing seamark features from existing 
general osm2pgsql tables, this is slow due to missing indexes
and a large data volumne in the tables in general.

In the long run we should have a separate osm2pgsql flex
import into appropriate sea map specific tables. A lot
of preprocessing, like generating labels, replacing colors
etc. could than also be done at import time instead of doing
so in SQL queries or <Filter> rules at render time again and
again.

