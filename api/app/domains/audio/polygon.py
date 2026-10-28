def check_polygon(value):
    """An audience area is either empty or a closed shape of at least three corners."""
    if value is None or value == []:
        return value
    if len(value) < 3:
        raise ValueError("An audience area needs at least three corners")
    for corner in value:
        if len(corner) != 2:
            raise ValueError("Each corner is an [x, y] pair")
    return value
