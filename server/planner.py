"""The route math: which places to visit, in what order, at what times.

Model: one "vehicle" (the traveler) leaves a start point at a start time and must
reach the requested end point by the deadline. Every place is optional (prize-collecting):
skipping one costs its score, so the solver fits the most valuable set of stops.
Opening hours are time windows, visit lengths are service times, meals must land
in lunch or dinner hours, viewpoints lean toward golden hour, and switching
neighborhoods costs points so the day forms blocks. Hours with rain in the
forecast make outdoor stops worth less, so they get pushed to dry hours.
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
MEALS = {"lunch": LUNCH, "dinner": DINNER}
MIN_SCORE = 25               # below this, a place is a poor match and never planned
DINNER_POINTS = 1000         # skipping dinner costs more than all optional stops, less than a must-see
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
    appointment_time: int | None = None  # fixed local start time, minutes after midnight


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
    locked: set = field(default_factory=set)   # nodes the user forced into the plan
    forecast: list = field(default_factory=list)            # hourly {hour, prob, mm}; empty if unavailable
    rain_hours: set = field(default_factory=set)            # local hours when rain is expected
    tired: bool = False
    route: list = field(default_factory=list)
    initial_route: list = field(default_factory=list)
    meal_slot: dict = field(default_factory=dict)          # node -> "lunch" / "dinner" the solver picked
    initial_meal_slot: dict = field(default_factory=dict)
    weather_slot: dict = field(default_factory=dict)       # node -> "dry" / "wet" the solver picked
    initial_weather_slot: dict = field(default_factory=dict)
    polylines: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)          # node -> (lat, lng) for live positions
    changed: set = field(default_factory=set)
    dropped: list = field(default_factory=list)
    compare: dict | None = None

    def cand(self, node: int) -> Cand:
        return self.cands[node - 1]

    def point(self, node: int) -> tuple[float, float]:
        if node in self.positions:
            return self.positions[node]
        if node == 0:
            return (self.hotel["lat"], self.hotel["lng"])
        if node == self.end_node:
            return (self.end_location["lat"], self.end_location["lng"])
        c = self.cand(node)
        return (c.lat, c.lng)

    def wet(self, start: int, end: int | None = None) -> bool:
        """Whether rain is expected at minute start, or anywhere in [start, end)."""
        last = start if end is None else end - 1
        return any(h in self.rain_hours for h in range(start // 60, last // 60 + 1))

    @property
    def raining(self) -> bool:
        return self.wet(self.now)

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


def spells(hours: set) -> list:
    """Runs of consecutive hours, as (start, end) minutes after midnight."""
    out = []
    for h in sorted(hours):
        if out and out[-1][1] == 60 * h:
            out[-1] = (out[-1][0], 60 * h + 60)
        else:
            out.append((60 * h, 60 * h + 60))
    return out


def complement(iv: list, lo: int = 0, hi: int = 1439) -> list:
    out = []
    for a, b in iv:
        if a > lo:
            out.append((lo, a - 1))
        lo = max(lo, b + 1)
    if lo <= hi:
        out.append((lo, hi))
    return out


# ---------- per-node quantities ----------

def points(s: Session, node: int, weather: str = "dry") -> float:
    c = s.cand(node)
    p = c.score / 4
    if weather == "wet":
        p *= RAIN_FACTOR.get(c.setting, 1)
    return p


def visit_len(s: Session, node: int) -> int:
    c = s.cand(node)
    return max(15, round(c.visit_min * PACE.get(s.trip.get("pace", "normal"), 1) / 5) * 5)


def meals_had(s: Session) -> set:
    return {n for x in s.completed for n in x["notes"] if n in MEALS}


def appointment_meal(c) -> str:
    """Which meal a reservation stands in for: lunch before mid-afternoon, else dinner."""
    return "lunch" if c.appointment_time < (LUNCH[1] + DINNER[0]) // 2 else "dinner"


def allowed_starts(s: Session, node: int, t0: int, slots: list = (LUNCH, DINNER),
                   weather: str | None = None) -> list:
    """Time intervals when a visit to this node may start. Meals must start in one of the slots.
    weather "dry" or "wet" keeps visits that count as out of or in the forecast rain."""
    c, v = s.cand(node), visit_len(s, node)
    iv = [(o, cl - v) for o, cl in c.windows if cl - v >= o]
    # An explicit reservation overrides the generic lunch/dinner suggestions.
    if c.kind == "meal" and c.appointment_time is None:
        iv = intersect(iv, list(slots))
    if weather:
        # Visits that are only partly in the rain count as whichever is worth less for this place.
        dry = [(lo, hi - v) for lo, hi in spells(set(range(24)) - s.rain_hours) if hi - v >= lo]
        wet = [(lo, hi - v) for lo, hi in spells(s.rain_hours) if hi - v >= lo]
        if RAIN_FACTOR.get(c.setting, 1) < 1:
            wet = complement(dry)
        else:
            dry = complement(wet)
        iv = intersect(iv, dry if weather == "dry" else wet)
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


def add_position(s: Session, pt: tuple[float, float], walk: list, walk_m: list, transit: list,
                 drive: list | None = None) -> int:
    """Add the traveler's live position as a new node, given travel times from it to every
    existing node. Nothing is ever planned to it, so its column stays empty. Returns the node."""
    node = len(s.walk)
    for m, row in ((s.walk, walk), (s.walk_m, walk_m), (s.transit, transit), (s.drive, drive)):
        if m is None:
            continue
        for r in m:
            r.append(None)
        m.append(list(row) + [0])
    s.positions[node] = pt
    return node


# ---------- schedule a fixed route ----------

def simulate(s: Session, route: list, t0: int, start_node: int) -> dict | None:
    t, loc, stops, had = t0, start_node, [], meals_had(s)
    for node in route:
        L = leg(s, loc, node)
        arrive = t + L["min"]
        c = s.cand(node)
        pinned = s.meal_slot.get(node)
        slots = [MEALS[pinned]] if pinned else [w for m, w in MEALS.items() if m not in had]
        starts = allowed_starts(s, node, t0, slots, s.weather_slot.get(node))
        if c.appointment_time is not None:
            fixed = c.appointment_time
            begin = fixed if arrive <= fixed and any(lo <= fixed <= hi for lo, hi in starts) else None
        else:
            begin = next((max(arrive, lo) for lo, hi in starts if hi >= arrive), None)
        if begin is None:
            return None
        leave = begin + visit_len(s, node)
        notes = []
        if c.appointment_time is not None:
            notes.append("appointment")
        if c.kind == "meal" and LUNCH[0] <= begin <= LUNCH[1]:
            notes.append("lunch")
        if c.kind == "meal" and DINNER[0] <= begin <= DINNER[1]:
            notes.append("dinner")
        if c.kind == "meal" and c.appointment_time is not None and not set(notes) & set(MEALS):
            notes.append(appointment_meal(c))
        if (s.sunset and c.kind == "viewpoint" and c.setting != "indoor" and not s.wet(begin, leave)
                and s.sunset - 80 <= begin <= s.sunset):
            notes.append("golden")
        if s.wet(begin, leave):
            notes.append("rain")
        had |= set(notes) & set(MEALS)
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
    # A meal becomes one copy per meal slot still open (only one copy can be picked),
    # so the solver can cap lunch and dinner at one each. A meal reservation is a
    # single copy that counts as the meal nearest its time. Every place also gets a
    # copy for visits that avoid forecast rain and one for visits that overlap it,
    # worth RAIN_FACTOR as much.
    had = meals_had(s)
    snacked = any(s.cand(x["node"]).kind == "snack" for x in s.completed)
    entries = []                                  # (node, meal slot or None, "dry" / "wet")
    for k in cand_nodes:
        c = s.cand(k)
        required = c.must or c.appointment_time is not None or k in s.locked
        if (c.score < MIN_SCORE or c.kind == "snack" and snacked) and not required:
            continue
        if c.kind == "meal" and c.appointment_time is not None:
            meals = [appointment_meal(c) if appointment_meal(c) not in had else None]
        elif c.kind == "meal":
            meals = [x for x in MEALS if x not in had]
        else:
            meals = [None]
        for m in meals:
            slots = [MEALS[m]] if m else list(MEALS.values())
            for w in ("dry", "wet"):
                iv = allowed_starts(s, k, t0, slots, w)
                if c.appointment_time is not None:   # only the copy whose weather covers the fixed time
                    iv = [(lo, hi) for lo, hi in iv if lo <= c.appointment_time <= hi]
                if iv:
                    entries.append((k, m, w))
    nodes = [start_node, s.end_node] + [k for k, _, _ in entries]  # local 0 = start, local 1 = trip end
    slot = [None, None] + [m for _, m, _ in entries]
    weather = [None, None] + [w for _, _, w in entries]
    n = len(nodes)
    T = [[0 if i == j else leg(s, nodes[i], nodes[j])["min"] for j in range(n)] for i in range(n)]
    visit = [0, 0] + [visit_len(s, k) for k, _, _ in entries]
    zone = [None, None] + [s.cand(k).zone for k, _, _ in entries]
    start_zone = s.cand(start_node).zone if 0 < start_node <= len(s.cands) else None
    # Skipping a place costs its best copy's points; visiting a copy costs what it gives up against that.
    value = [0, 0] + [points(s, k, w) for k, _, w in entries]
    best = {}
    for li in range(2, n):
        best[nodes[li]] = max(best.get(nodes[li], 0), value[li])
    extra = [0, 0] + [int((best[nodes[li]] - value[li]) * SCALE) for li in range(2, n)]

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
        c = travel_w * T[a][b] + extra[b]
        za = start_zone if a == 0 else zone[a]
        if switch and b >= 2 and za is not None and za != zone[b]:
            c += switch
        return c
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(cost_cb))

    # A late reservation may be the only stop left, so waiting must be able to
    # span the traveler's whole remaining day rather than stopping at four hours.
    routing.AddDimension(time_idx, max(240, s.deadline - t0), s.deadline, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    time_dim.CumulVar(routing.Start(0)).SetRange(t0, t0)
    time_dim.CumulVar(routing.End(0)).SetMax(s.deadline)

    for m in MEALS:                                                     # at most one lunch, one dinner
        meal_idx = routing.RegisterUnaryTransitCallback(
            lambda i, m=m: 1 if slot[manager.IndexToNode(i)] == m else 0)
        routing.AddDimension(meal_idx, 0, 1, True, m)
    if "dinner" in slot:                                                # dinner is expected when it fits
        routing.GetDimensionOrDie("dinner").SetCumulVarSoftLowerBound(
            routing.End(0), 1, DINNER_POINTS * SCALE)

    snack_idx = routing.RegisterUnaryTransitCallback(
        lambda i: 1 if manager.IndexToNode(i) >= 2 and s.cand(nodes[manager.IndexToNode(i)]).kind == "snack" else 0)
    routing.AddDimension(snack_idx, 0, 1, True, "snacks")             # at most one snack

    copies = {}
    for li in range(2, n):
        k, idx = nodes[li], manager.NodeToIndex(li)
        iv = allowed_starts(s, k, t0, [MEALS[slot[li]]] if slot[li] else list(MEALS.values()), weather[li])
        cum = time_dim.CumulVar(idx)
        c = s.cand(k)
        if c.appointment_time is not None:
            # Reservations and shows start at their stated time, not merely near it.
            cum.SetRange(c.appointment_time, c.appointment_time)
        else:
            cum.SetRange(iv[0][0], iv[-1][1])
            for (_, hi), (lo, _) in zip(iv, iv[1:]):
                if lo - hi > 1:
                    cum.RemoveInterval(hi + 1, lo - 1)
        if s.sunset and c.kind == "viewpoint" and c.setting != "indoor" and not s.wet(s.sunset - 75, s.sunset):
            time_dim.SetCumulVarSoftLowerBound(idx, s.sunset - 75, 25)
            time_dim.SetCumulVarSoftUpperBound(idx, s.sunset, 50)
        copies.setdefault(k, []).append(idx)
    for k, idxs in copies.items():
        c = s.cand(k)
        required = c.must or c.appointment_time is not None or k in s.locked
        penalty = int(best[k] * SCALE) + (10**7 if required else 0)
        routing.AddDisjunction(idxs, penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_s

    sol = routing.SolveWithParameters(params)
    if sol is None:
        return []
    route, s.meal_slot, s.weather_slot = [], {}, {}
    i = sol.Value(routing.NextVar(routing.Start(0)))
    while not routing.IsEnd(i):
        li = manager.IndexToNode(i)
        route.append(nodes[li])
        if slot[li]:
            s.meal_slot[nodes[li]] = slot[li]
        s.weather_slot[nodes[li]] = weather[li]
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
        if c.score < MIN_SCORE and not c.must:
            why = c.reason or "Not a great match for you"
        elif not c.windows:
            why = "Closed that day"
        elif not allowed_starts(s, k, t0):
            why = "Its hours don't fit your time window"
        elif c.kind == "snack" and any(s.cand(x).kind == "snack" for x in in_plan):
            why = "One snack stop is enough for the day"
        elif c.setting == "outdoor" and not allowed_starts(s, k, t0, weather="dry"):
            why = "Outdoors, and rain is expected whenever it would fit"
        elif s.blocks and c.zone not in zones:
            why = f"Would add a separate trip out to {c.zone_name}"
        else:
            why = "Less worth it per minute than the stops that made the cut"
        out.append({"id": c.id, "name": c.name, "why": why, "score": c.score})
    return sorted(out, key=lambda x: -x["score"])
