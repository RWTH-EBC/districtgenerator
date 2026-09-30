"""Click Run once to refresh the shared Aachen OSM source cache.

Preserves previous source files in cache_backups. Does not construct districts,
classify candidates, change the parameter workbook or regenerate maps.
"""
from pathlib import Path

from aachen_osm_pilot import download


if __name__ == '__main__':
    source = Path(__file__).resolve().parent / 'results' / 'aachen_osm_pilot_v2'
    print('Refreshing the shared Aachen OSM data. This may take some time.', flush=True)
    _, features = download(source, refresh=True)
    print(f'Saved {len(features):,} source features to {source}', flush=True)
    print('Finished. Future normal Aachen runs will reuse these data.')
