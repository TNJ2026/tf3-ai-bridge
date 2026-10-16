"""Bounded schemas shared by no_gui-only workflow adapters."""
import math
import re


def entity(value):
    return type(value) is int and 0 <= value < 2147483647


def component_names(value):
    return (isinstance(value, list) and 1 <= len(value) <= 16
            and len(set(str(x) for x in value)) == len(value)
            and all(isinstance(x, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', x) for x in value))


def line_edits(value):
    """Existing stop indices retain native waypoint/alternative-terminal objects."""
    if not isinstance(value, list) or not 2 <= len(value) <= 32:
        return False
    allowed = {'source_index', 'station_group', 'station', 'terminal', 'loads',
               'max_load', 'force_unload', 'extra_wait'}
    for stop in value:
        if not isinstance(stop, dict) or not stop or not stop.keys() <= allowed:
            return False
        if ('source_index' in stop) == ('station_group' in stop):
            return False
        if 'source_index' in stop and not (type(stop['source_index']) is int and 0 <= stop['source_index'] < 32):
            return False
        if 'station_group' in stop and (not entity(stop['station_group']) or not {'station', 'terminal', 'loads'} <= stop.keys()):
            return False
        for key in ('station', 'terminal'):
            if key in stop and not (type(stop[key]) is int and 0 <= stop[key] < 64):
                return False
        if 'loads' in stop:
            ids = stop['loads']
            if not isinstance(ids, list) or len(ids) > 8 or not all(entity(x) and x <= 255 for x in ids) or len(set(ids)) != len(ids):
                return False
        if 'max_load' in stop and not (type(stop['max_load']) in (int, float) and math.isfinite(stop['max_load']) and 0 <= stop['max_load'] <= 1):
            return False
        if 'force_unload' in stop and type(stop['force_unload']) is not bool:
            return False
        if 'extra_wait' in stop and not (type(stop['extra_wait']) is int and 0 <= stop['extra_wait'] <= 600):
            return False
    return True
