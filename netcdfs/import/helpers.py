from hashlib import md5
from numpy import format_float_positional


class NoMatchingUnitError(Exception):
    def __init__(self, unit):
        self.unit = unit


def to_hash(grid, lon, lat):
    """Create a hash of values to connect this value to the coordinate
    table."""
    s = ""
    if grid == "GCM":
        s = "{}SRID=4326;POINT({:.2f} {:.2f})".format(grid, lon, lat)
    elif grid == "RCM":
        s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(grid, lon, lat)
    else:
        raise NoMatchingUnitError(grid)
    hashed = md5(s.encode()).hexdigest()

    return hashed


def stat_fmt(pandas_value, unit):
    if unit == "z-score":
        formatted_value = format_float_positional(pandas_value, precision=1)
        return formatted_value
    else:
        int_value = int(pandas_value)
        return int_value


def to_remo_stat_new(row):
    """Make a stat from the output of our dataframe."""
    (
        lon,
        lat,
        warming_levels,
        dataset_id,
        grid,
        unit,
        values,
    ) = row
    lon = lon + 0  # +0 incase we have lon = -0 so it becomes 0
    lat = lat + 0  # +0 incase we have lat = -0 so it becomes 0
    hashed = to_hash(grid, lon, lat)

    stat_dict = {
        "dataset_id": int(dataset_id),  # Because we inserted it into the numpy array
        "coordinate_hash": hashed,
        "warming_scenario": str(warming_levels),
        "vaules": [stat_fmt(num, unit) for num in values],
    }

    return stat_dict


class NoMatchingGridError(Exception):
    def __init__(self, grid):
        self.grid = grid


class NoDatasetWithThatIDError(Exception):
    def __init__(self, ident):
        self.ident = ident
