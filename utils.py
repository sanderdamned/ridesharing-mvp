from datetime import datetime, time

def format_departure(dep):
    if isinstance(dep, time):
        return dep.strftime("%H:%M:%S")
    if isinstance(dep, str):
        try:
            dt = datetime.strptime(dep, "%H:%M")
            return dt.strftime("%H:%M:%S")
        except:
            return dep
    return str(dep)

def validate_coordinates(coords):
    if not isinstance(coords, list) or len(coords) != 2:
        return False
    try:
        float(coords[0])
        float(coords[1])
        return True
    except ValueError:
        return False
