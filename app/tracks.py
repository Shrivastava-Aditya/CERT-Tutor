"""Load content/tracks.yaml and work out where each station sits on the tracks map."""
from pathlib import Path

import yaml

COL_X = [190, 460, 730]   # x of each column's stations
MAP_WIDTH = 860
HEADER_H = 50             # room for the column titles
LANE_GAP = 90             # vertical distance from main line to branch
ROW_PAD = 72              # space below a track's last line, for labels


def _path(a: dict, b: dict) -> str:
    """Straight line on the same lane, an S-curve when the line branches."""
    if a["y"] == b["y"]:
        return f"M{a['x']} {a['y']} H{b['x']}"
    mid = (a["x"] + b["x"]) / 2
    return f"M{a['x']} {a['y']} C{mid} {a['y']} {mid} {b['y']} {b['x']} {b['y']}"


def load_tracks(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    y = HEADER_H
    tracks = []
    for t in data["tracks"]:
        main_y = y + 30
        by_id = {}
        for c in t["certs"]:
            c["x"] = COL_X[c["col"]]
            c["y"] = main_y + c.get("lane", 0) * LANE_GAP
            by_id[c["id"]] = c
        segments = [
            {"d": _path(by_id[c["after"]], c), "active": c.get("status") == "active"}
            for c in t["certs"]
            if c.get("after") in by_id
        ]
        lanes = max(c.get("lane", 0) for c in t["certs"])
        tracks.append({**t, "main_y": main_y, "segments": segments})
        y = main_y + lanes * LANE_GAP + ROW_PAD
    return {
        "columns": [{"title": title, "x": COL_X[i]} for i, title in enumerate(data["columns"])],
        "tracks": tracks,
        "width": MAP_WIDTH,
        "height": y,
    }
