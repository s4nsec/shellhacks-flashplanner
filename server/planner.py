"""The route math: which places to visit, in what order, at what times.

Model: one "vehicle" (the traveler) leaves a start point at a start time and must
reach the requested end point by the deadline. Every place is optional (prize-collecting):
skipping one costs its score, so the solver fits the most valuable set of stops.
Opening hours are time windows, visit lengths are service times, meals must land
in lunch or dinner hours, viewpoints lean toward golden hour, and switching
neighborhoods costs points so the day forms blocks.
"""
import math
from dataclasses import dataclass, field
from datetime import date as Date

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

PACE = {"relaxed": 1.25, "normal": 1.0, "packed": 0.8}
WALK_CAP_KM = {"walk": (math.inf, 0.9), "transit": (1.3, 0.7), "ride": (1.0, 0.6)}  # (normal, tired)
RIDE_PICKUP_MIN = 4
SWITCH_POINTS = 5            # cost of moving to another neighborhood
TRAVEL_POINTS_PER_MIN = 0.03  # mild pressure against zigzagging
SCALE = 1000                 # OR-Tools needs integers: 1 point = 1000 cost units
LUNCH, DINNER = (690, 840), (1050, 1260)
KIND_DEFAULT_MIN = {"museum": 90, "meal": 60, "snack": 20, "market": 50, "park": 60,
                    "viewpoint": 30, "shopping": 45, "nightlife": 90, "sight": 45, "other": 40}
RAIN_FACTOR = {"outdoor": 0.25, "covered": 0.75, "indoor": 1.15}


@dataclass
class Cand:
    id: str
    name: str
    lat: float
    lng: float
    rating: float | None = None
    count: int = 0
    maps_uri: str = ""
    address: str = ""
    list_rank: int = 999          # position in Google's "top attractions" results
    hood: str = ""                # neighborhood from the address, if Google has one
    score: int = 0                # Gemini, 0-100
    kind: str = "sight"
    setting: str = "indoor"
    reason: str = ""
    visit_min: int = 45
    visit_source: str = "estimate"
    evidence: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    hours_known: bool = False
    zone: int = 0
    zone_name: str = ""
    must: bool = False


@dataclass
class Session:
    id: str
    trip: dict
    date: str
    weekday: int                  # Places convention, 0 = Sunday
    utc_offset: int
    sunset: int | None
    hotel: dict                   # start point: {name, lat, lng}
    end_location: dict            # requested end point; defaults to hotel
    end_node: int                 # 0 when ending at hotel, otherwise len(cands) + 1
    cands: list                   # candidate node k (k >= 1) is cands[k - 1]
    walk: list
    walk_m: list
    transit: list
    drive: list | None
    start: int
    deadline: int
    now: int = 0
    loc: int = 0
    completed: list = field(default_factory=list)
    skipped: set = field(default_factory=set)
    raining: bool = False
    tired: bool = False
    route: list = field(default_factory=list)
    initial_route: list = field(default_factory=list)
    polylines: dict = field(default_factory=dict)
    changed: set = field(default_factory=set)
    dropped: list = field(default_factory=list)
    compare: dict | None = None

    def cand(self, node: int) -> Cand:
        return self.cands[node - 1]

    def point(self, node: int) -> tuple[float, float]:
        if node == 0:
            return (self.hotel["lat"], self.hotel["lng"])
        if node == self.end_node:
            return (self.end_location["lat"], self.end_location["lng"])
        c = self.cand(node)
        return (c.lat, c.lng)

    @property
    def mode(self) -> str:
        return self.trip.get("getting_around", "transit")

    @property
    def blocks(self) -> bool:
        return bool(self.trip.get("by_neighborhood", True))


# ---------- helpers ----------

def haversine_km(a, b) -> float:
    r = math.pi / 180
    dl, dg = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    s = math.sin(dl / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dg / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(s))


def sunset_minutes(lat: float, lng: float, day: Date, utc_offset_min: int) -> int | None:
    """Local sunset in minutes after midnight (NOAA approximation, about 1-2 min accurate)."""
    g = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    la = math.radians(lat)
    x = math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)
    if abs(x) > 1:
        return None  # polar day or night
    ha = math.degrees(math.acos(x))
    utc = 720 - 4 * (lng - ha) - eqtime
    return int(round(utc + utc_offset_min)) % 1440


def assign_zones(cands: list[Cand], radius_km: float = 1.2) -> None:
    """Group places into neighborhoods by distance, then name each group."""
    clusters = []  # [lat, lng, members]
    for c in sorted(cands, key=lambda c: -c.score):
        best, best_d = None, radius_km
        for cl in clusters:
            d = haversine_km((c.lat, c.lng), (cl[0], cl[1]))
            if d <= best_d:
                best, best_d = cl, d
        if best is None:
            clusters.append([c.lat, c.lng, [c]])
        else:
            best[2].append(c)
            k = len(best[2])
            best[0] += (c.lat - best[0]) / k
            best[1] += (c.lng - best[1]) / k
    used = {}
    for i, cl in enumerate(clusters):
        hoods = [m.hood for m in cl[2] if m.hood]
        name = max(set(hoods), key=hoods.count) if hoods else f"Around {cl[2][0].name}"
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name} ({used[name]})"
        for m in cl[2]:
            m.zone, m.zone_name = i, name


def intersect(a: list, b: list) -> list:
    out = []
    for x1, y1 in a:
        for x2, y2 in b:
            lo, hi = max(x1, x2), min(y1, y2)
            if lo <= hi:
                out.append((lo, hi))
    return sorted(out)


# ---------- per-node quantities ----------

def points(s: Session, node: int) -> float:
    c = s.cand(node)
    p = c.score / 4
    if s.raining:
        p *= RAIN_FACTOR.get(c.setting, 1)
    return p


def visit_len(s: Session, node: int) -> int:
    c = s.cand(node)
    return max(15, round(c.visit_min * PACE.get(s.trip.get("pace", "normal"), 1) / 5) * 5)


def allowed_starts(s: Session, node: int, t0: int) -> list:
    """Time intervals when a visit to this node may start."""
    c, v = s.cand(node), visit_len(s, node)
    iv = [(o, cl - v) for o, cl in c.windows if cl - v >= o]
    if c.kind == "meal":
        iv = intersect(iv, [LUNCH, DINNER])
    return intersect(iv, [(t0, s.deadline - v)])


def leg(s: Session, a: int, b: int) -> dict:
    """Fastest allowed way from node a to node b, from the Routes API matrices."""
    if a == b:
        return {"mode": "walk", "min": 0, "km": 0.0}
    walk = s.walk[a][b]
    km = (s.walk_m[a][b] or 0) / 1000 if s.walk_m[a][b] is not None else None
    if walk is not None and s.tired:
        walk = math.ceil(walk * 1.25)
    cap = WALK_CAP_KM[s.mode][1 if s.tired else 0]
    if s.mode == "ride" and s.drive and s.drive[a][b] is not None:
        vehicle, vmode = s.drive[a][b] + RIDE_PICKUP_MIN, "ride"
    elif s.transit[a][b] is not None and (s.mode != "walk" or s.tired):
        vehicle, vmode = s.transit[a][b], "transit"
    else:
        vehicle, vmode = None, None
    if walk is not None and (km is not None and km <= cap or vehicle is None or walk <= vehicle):
        return {"mode": "walk", "min": max(1, walk), "km": round(km or 0, 2)}
    if vehicle is not None:
        return {"mode": vmode, "min": max(1, vehicle), "km": round(km or 0, 2)}
    return {"mode": "walk", "min": 9999, "km": 0.0}  # unreachable


# ---------- schedule a fixed route ----------

def simulate(s: Session, route: list, t0: int, start_node: int) -> dict | None:
    t, loc, stops = t0, start_node, []
    for node in route:
        L = leg(s, loc, node)
        arrive = t + L["min"]
        begin = next((max(arrive, lo) for lo, hi in allowed_starts(s, node, t0) if hi >= arrive), None)
        if begin is None:
            return None
        c = s.cand(node)
        leave = begin + visit_len(s, node)
        notes = []
        if c.kind == "meal" and LUNCH[0] <= begin <= LUNCH[1]:
            notes.append("lunch")
        if c.kind == "meal" and DINNER[0] <= begin <= DINNER[1]:
            notes.append("dinner")
        if (s.sunset and c.kind == "viewpoint" and c.setting != "indoor" and not s.raining
                and s.sunset - 80 <= begin <= s.sunset):
            notes.append("golden")
        stops.append({"node": node, "from": loc, "leg": L, "arrive": arrive, "begin": begin,
                      "wait": begin - arrive, "leave": leave, "notes": notes})
        t, loc = leave, node
    back = leg(s, loc, s.end_node)
    end = t + back["min"]
    if end > s.deadline:
        return None
    travel = sum(x["leg"]["min"] for x in stops) + back["min"]
    walk_km = sum(x["leg"]["km"] for x in stops if x["leg"]["mode"] == "walk")
    walk_km += back["km"] if back["mode"] == "walk" else 0
    return {"stops": stops, "back": {**back, "from": loc}, "end": end, "travel": travel,
            "walk_km": round(walk_km, 1), "see": sum(x["leave"] - x["begin"] for x in stops),
            "waited": sum(x["wait"] for x in stops)}


# ---------- OR-Tools ----------

def solve(s: Session, t0: int, start_node: int, cand_nodes: list, time_limit_s: int = 3) -> list:
    feasible = [k for k in cand_nodes if allowed_starts(s, k, t0)]
    nodes = [start_node, s.end_node] + feasible   # local 0 = start, local 1 = trip end
    n = len(nodes)
    T = [[0 if i == j else leg(s, nodes[i], nodes[j])["min"] for j in range(n)] for i in range(n)]
    visit = [0, 0] + [visit_len(s, k) for k in feasible]
    zone = [None, None] + [s.cand(k).zone for k in feasible]
    start_zone = s.cand(start_node).zone if start_node != 0 else None

    manager = pywrapcp.RoutingIndexManager(n, 1, [0], [1])
    routing = pywrapcp.RoutingModel(manager)

    def time_cb(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        return visit[a] + T[a][b]
    time_idx = routing.RegisterTransitCallback(time_cb)

    switch = int(SWITCH_POINTS * SCALE) if s.blocks else 0
    travel_w = int(TRAVEL_POINTS_PER_MIN * SCALE)

    def cost_cb(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        c = travel_w * T[a][b]
        za = start_zone if a == 0 else zone[a]
        if switch and b >= 2 and za is not None and za != zone[b]:
            c += switch
        return c
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(cost_cb))

    routing.AddDimension(time_idx, 240, s.deadline, False, "Time")   # up to 4h waiting
    time_dim = routing.GetDimensionOrDie("Time")
    time_dim.CumulVar(routing.Start(0)).SetRange(t0, t0)
    time_dim.CumulVar(routing.End(0)).SetMax(s.deadline)

    meal_idx = routing.RegisterUnaryTransitCallback(
        lambda i: 1 if manager.IndexToNode(i) >= 2 and s.cand(nodes[manager.IndexToNode(i)]).kind == "meal" else 0)
    routing.AddDimension(meal_idx, 0, 2, True, "Meals")                # at most two meals

    for li in range(2, n):
        k, idx = nodes[li], manager.NodeToIndex(li)
        iv = allowed_starts(s, k, t0)
        cum = time_dim.CumulVar(idx)
        cum.SetRange(iv[0][0], iv[-1][1])
        for (_, hi), (lo, _) in zip(iv, iv[1:]):
            if lo - hi > 1:
                cum.RemoveInterval(hi + 1, lo - 1)
        c = s.cand(k)
        if s.sunset and c.kind == "viewpoint" and c.setting != "indoor" and not s.raining:
            time_dim.SetCumulVarSoftLowerBound(idx, s.sunset - 75, 25)
            time_dim.SetCumulVarSoftUpperBound(idx, s.sunset, 50)
        penalty = int(points(s, k) * SCALE) + (10**7 if c.must else 0)
        routing.AddDisjunction([idx], penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_s

    sol = routing.SolveWithParameters(params)
    if sol is None:
        return []
    route, i = [], sol.Value(routing.NextVar(routing.Start(0)))
    while not routing.IsEnd(i):
        route.append(nodes[manager.IndexToNode(i)])
        i = sol.Value(routing.NextVar(i))
    while route and simulate(s, route, t0, start_node) is None:
        route.pop()  # safety net; the model and simulate() use the same numbers
    return route


def naive(s: Session, t0: int, start_node: int, cand_nodes: list) -> list:
    """Baseline: go down Google's 'top attractions' list in order, skipping what doesn't fit."""
    order = sorted((k for k in cand_nodes if s.cand(k).score >= 40),
                   key=lambda k: (s.cand(k).list_rank, -s.cand(k).score))
    route = []
    for k in order:
        if simulate(s, route + [k], t0, start_node):
            route.append(k)
    return route


def cut_reasons(s: Session, cand_nodes: list, route: list, t0: int) -> list:
    in_plan = set(route) | {x["node"] for x in s.completed}
    zones = {s.cand(k).zone for k in in_plan}
    out = []
    for k in cand_nodes:
        if k in in_plan:
            continue
        c = s.cand(k)
        if c.score < 25:
            why = c.reason or "Not a great match for you"
        elif not c.windows:
            why = "Closed that day"
        elif not allowed_starts(s, k, t0):
            why = "Its hours don't fit your time window"
        elif s.raining and c.setting == "outdoor":
            why = "Outdoors, and it's raining"
        elif s.blocks and c.zone not in zones:
            why = f"Would add a separate trip out to {c.zone_name}"
        else:
            why = "Less worth it per minute than the stops that made the cut"
        out.append({"name": c.name, "why": why, "score": c.score})
    return sorted(out, key=lambda x: -x["score"])
