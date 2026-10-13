"""Load content/tracks.yaml and work out where each station sits on the tracks map.

Every provider gets its own SVG. Inside it, each lane (role line) is a horizontal
line; stations sit in columns (Start, Core, Advanced, Specialty).
"""
from pathlib import Path

import yaml

COL_X = [250, 440, 630, 820]  # x of each column's stations
WIDTH = 900
LANE_X0 = 176                 # where every lane's line starts (after its label)
TOP = 70                      # y of the first lane (column titles sit above it)
LANE_GAP = 84                 # vertical distance between lanes
BOTTOM = 66                   # room under the last lane for station labels


def _layout_track(track: dict) -> dict:
    lanes = []
    count = studying = passed = 0
    for i, lane in enumerate(track["lanes"]):
        y = TOP + i * LANE_GAP
        certs = lane["certs"]
        if lane.get("spread"):
            step = (COL_X[-1] - COL_X[0]) / max(len(certs) - 1, 1)
            xs = [COL_X[0] + k * step for k in range(len(certs))]
        else:
            xs = [COL_X[c["col"]] for c in certs]

        stations, segments = [], []
        prev_x = LANE_X0
        for c, x in zip(certs, xs):
            stations.append({**c, "x": round(x), "y": y, "status": c.get("status", "planned")})
            segments.append({
                "d": f"M{round(prev_x)} {y} H{round(x)}",
                "lead": prev_x == LANE_X0,          # the stub from the lane label: drawn fainter
                "active": c.get("status") == "active",
            })
            prev_x = x
        lanes.append({**lane, "y": y, "stations": stations, "segments": segments,
                      "sec": any(c.get("sec") for c in certs)})

        count += len(certs)
        studying += sum(c.get("status") == "active" for c in certs)
        passed += sum(c.get("status") == "done" for c in certs)

    return {
        **track,
        "lanes": lanes,
        "height": TOP + (len(lanes) - 1) * LANE_GAP + BOTTOM,
        "count": count,
        "studying": studying,
        "passed": passed,
    }


def load_tracks(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    tracks = [_layout_track(t) for t in data["tracks"]]
    return {
        "columns": [{"title": title, "x": COL_X[i]} for i, title in enumerate(data["columns"])],
        "tracks": tracks,
        "width": WIDTH,
        "total": sum(t["count"] for t in tracks),
        "studying": sum(t["studying"] for t in tracks),
        "passed": sum(t["passed"] for t in tracks),
    }
