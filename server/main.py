"""Sightline API server.

Run from the project root:
    uvicorn server.main:app --reload
then open http://localhost:8000

/api/plan and /api/replan stream newline-delimited JSON: "step" events as each
stage runs (for the agent trace), then one "plan" event, or an "error" event.
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from . import config, gemini, places, planner, routes, weather
from .models import InterpretRequest, ParseRequest, ReplanRequest, TripRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sightline")

app = FastAPI(title="Sightline")
WEB = Path(__file__).resolve().parent.parent / "web"
SESSIONS: dict[str, planner.Session] = {}   # in memory, one per planned day
SESSION_TOUCHED: dict[str, float] = {}
SESSION_TTL_SECONDS = 6 * 60 * 60
MAX_SESSIONS = 50
SHORTLIST = 20        # places that get reviews, travel times and a place in the solver
MAX_CANDIDATES = 40   # places Gemini scores
MODE_API = {"walk": "WALK", "transit": "TRANSIT", "ride": "DRIVE"}


# ---------- small helpers ----------

def to_min(hhmm: str | None, default: int) -> int:
    try:
        h, m = (hhmm or "").split(":")
        return max(0, min(1439, int(h) * 60 + int(m)))
    except ValueError:
        return default


def fmt(m: int) -> str:
    m = int(round(m))
    h, mm = (m // 60) % 24, m % 60
    return f"{(h + 11) % 12 + 1}:{mm:02d} {'pm' if h >= 12 else 'am'}"


def ev(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def step_run(key, title, call, source):
    return ev(type="step", key=key, status="run", title=title, call=call, source=source)


def step_ok(key, t0, result, detail=None):
    return ev(type="step", key=key, status="ok", result=result, detail=detail,
              ms=int((time.perf_counter() - t0) * 1000))


def explain_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        try:
            msg = e.response.json().get("error", {}).get("message", "")
        except ValueError:
            msg = e.response.text[:300]
        api = "Places API (New)" if "places.googleapis" in str(e.request.url) else "Routes API"
        return (f"{api} returned {e.response.status_code}: {msg} "
                f"Check that {api} is enabled for GOOGLE_MAPS_API_KEY and that billing is on.")
    if isinstance(e, httpx.HTTPError):
        return f"Couldn't reach Google Maps: {e}"
    return f"{type(e).__name__}: {e}"


def missing_keys_message() -> str | None:
    miss = config.missing_keys()
    if miss:
        return f"Add {' and '.join(miss)} to the .env file in the project root, then restart the server."
    return None


def evict_old_sessions(now: float | None = None) -> None:
    if now is None:
        now = time.time()
    cutoff = now - SESSION_TTL_SECONDS
    expired = [sid for sid, touched in SESSION_TOUCHED.items() if touched < cutoff]
    for sid in expired:
        SESSION_TOUCHED.pop(sid, None)
        SESSIONS.pop(sid, None)
    if len(SESSIONS) <= MAX_SESSIONS:
        return
    oldest = sorted(SESSION_TOUCHED, key=SESSION_TOUCHED.get)
    for sid in oldest[:len(SESSIONS) - MAX_SESSIONS]:
        SESSION_TOUCHED.pop(sid, None)
        SESSIONS.pop(sid, None)


def remember_session(s: planner.Session) -> None:
    SESSION_TOUCHED[s.id] = time.time()
    SESSIONS[s.id] = s
    evict_old_sessions()


def get_session(session_id: str) -> planner.Session | None:
    evict_old_sessions()
    s = SESSIONS.get(session_id)
    if s:
        SESSION_TOUCHED[session_id] = time.time()
    return s


# ---------- pages & config ----------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def get_config():
    return {"mapsKey": config.MAPS_BROWSER_KEY, "mapId": config.MAP_ID,
            "missing": config.missing_keys(), "model": config.GEMINI_MODEL}


@app.get("/api/demo")
def demo_plan():
    """Static Montreal plan for judging tables when API keys or quotas are unavailable."""
    hotel = {"name": "Sheraton Montreal downtown", "lat": 45.5009, "lng": -73.5738}
    stops = [
        _demo_stop("Notre-Dame Basilica", 45.5045, -73.5561, 615, 625, 685, "Vieux-Montreal",
                   "sight", "indoor", "Iconic architecture and a compact first stop.", 4.7, 38215,
                   {"mode": "transit", "min": 10, "km": 1.5}, "reviews"),
        _demo_stop("Old Port of Montreal", 45.5076, -73.5517, 693, 693, 743, "Vieux-Montreal",
                   "park", "outdoor", "Waterfront views without committing the whole day.", 4.6, 30144,
                   {"mode": "walk", "min": 8, "km": 0.6}, "gemini"),
        _demo_stop("Jean-Talon Market", 45.5352, -73.6141, 770, 770, 840, "Little Italy",
                   "meal", "covered", "Lunch fits the food brief and keeps the route lively.", 4.6, 28102,
                   {"mode": "transit", "min": 27, "km": 5.8}, "reviews", ["lunch"]),
        _demo_stop("Mount Royal Lookout", 45.5039, -73.5878, 915, 915, 960, "Mount Royal",
                   "viewpoint", "outdoor", "Best city view near golden hour.", 4.8, 19762,
                   {"mode": "transit", "min": 35, "km": 6.2}, "default", ["golden"]),
        _demo_stop("Bar George", 45.5016, -73.5766, 982, 1050, 1110, "Downtown",
                   "meal", "indoor", "Dinner lands close to the hotel in a historic room.", 4.4, 3951,
                   {"mode": "walk", "min": 22, "km": 1.4}, "gemini", ["dinner"]),
    ]
    back = {"mode": "walk", "min": 7, "km": 0.5, "polyline": None}
    return {
        "session_id": "demo", "demo": True, "city": "Montreal", "date": Date.today().isoformat(),
        "start": 600, "deadline": 1140, "now": 600, "sunset": 1115,
        "raining": False, "tired": False,
        "trip": {"city": "Montreal", "date": None, "start_time": "10:00", "end_time": "19:00",
                 "start_location": "Sheraton downtown", "loves": ["architecture", "food", "views"],
                 "skips": ["museums"], "must_see": [], "pace": "normal",
                 "getting_around": "transit", "by_neighborhood": True, "user_list": []},
        "hotel": hotel, "end_location": hotel, "at": hotel["name"], "shifted": False,
        "completed": [], "stops": stops, "back": back, "end": 1117,
        "blocks": [
            {"zone": "Vieux-Montreal", "from": 625, "to": 743, "count": 2},
            {"zone": "Little Italy", "from": 770, "to": 840, "count": 1},
            {"zone": "Mount Royal", "from": 915, "to": 960, "count": 1},
            {"zone": "Downtown", "from": 1050, "to": 1110, "count": 1},
        ],
        "summary": {"stops": 5, "walk_km": 2.5, "moving": 109, "zones": 4},
        "others": [
            {"name": "Montreal Museum of Fine Arts", "lat": 45.4986, "lng": -73.5795},
            {"name": "La Fontaine Park", "lat": 45.5278, "lng": -73.5690},
            {"name": "Atwater Market", "lat": 45.4793, "lng": -73.5779},
        ],
        "cuts": [
            {"name": "Montreal Museum of Fine Arts", "why": "Museums were on the skip list", "score": 20},
            {"name": "La Fontaine Park", "why": "Would add a separate trip east", "score": 48},
            {"name": "Atwater Market", "why": "Jean-Talon was a stronger food stop", "score": 56},
        ],
        "dropped": [],
        "story": ("Demo plan: five stops fit between 10:00 am and 7:00 pm, grouped into neighborhood blocks "
                  "so the day is easy to explain to judges. Lunch lands at Jean-Talon Market, the lookout is "
                  "timed near sunset, and you're back downtown with time to spare."),
        "compare": {
            "window": 540,
            "plan": {"stops": 5, "see": 295, "travel": 109, "waited": 68},
            "naive": {"stops": 4, "see": 230, "travel": 156, "waited": 35},
        },
    }


def _demo_stop(name, lat, lng, arrive, begin, leave, zone, kind, setting, reason,
               rating, count, leg, source, notes=None):
    return {
        "id": "demo-" + name.lower().replace(" ", "-"),
        "name": name, "lat": lat, "lng": lng,
        "arrive": arrive, "begin": begin, "wait": begin - arrive, "leave": leave,
        "leg": {**leg, "polyline": None}, "notes": notes or [], "done": False, "new": False,
        "visit": {"minutes": leave - begin, "base": leave - begin, "source": source, "evidence": []},
        "zone": zone, "kind": kind, "setting": setting, "reason": reason,
        "rating": rating, "count": count, "maps_uri": "", "hours_known": True, "opens": None,
    }


# ---------- 1. understand the message ----------

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def resolve_relative_day(relative: str, today: Date) -> Date | None:
    """Resolve "today", "tomorrow" or a weekday name against `today` (the city's date).

    A weekday means the next one on or after today.
    """
    relative = (relative or "").strip().lower()
    if relative == "today":
        return today
    if relative == "tomorrow":
        return today + timedelta(days=1)
    if relative in WEEKDAYS:
        return today + timedelta(days=(WEEKDAYS.index(relative) - today.weekday()) % 7)
    return None


def local_date(utc_offset_minutes: int, now_utc: datetime | None = None) -> Date:
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc + timedelta(minutes=utc_offset_minutes)).date()


async def city_today(city: str, start_location: str = "") -> Date:
    """Today's date where the traveler is going. Falls back to the UTC date."""
    if config.MAPS_KEY and city:
        query = f"{start_location}, {city}" if start_location else city
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                hits = await places.search_text(http, query, 1)
            if hits and "utcOffsetMinutes" in hits[0]:
                return local_date(hits[0]["utcOffsetMinutes"])
        except Exception:  # noqa: BLE001  (use UTC rather than fail the parse)
            pass
    return local_date(0)


@app.post("/api/parse")
async def parse(req: ParseRequest):
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Add GEMINI_API_KEY to the .env file, then restart the server.")
    try:
        p = await gemini.parse_trip(req.message, local_date(0).isoformat())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gemini couldn't read the message: {e}")
    date = p.date or None
    if p.relative_day:
        day = resolve_relative_day(p.relative_day, await city_today(p.city, p.start_location))
        date = day.isoformat() if day else date
    return {
        "city": p.city,
        "date": date,
        "start_time": p.start_time or None,
        "end_time": p.end_time or None,
        "start_location": p.start_location or None,
        "end_location": p.end_location or None,
        "loves": p.loves, "skips": p.skips, "must_see": p.must_see,
        "appointments": [a.model_dump() for a in p.appointments],
        "pace": p.pace if p.pace in planner.PACE else "normal",
        "getting_around": p.getting_around if p.getting_around in MODE_API else "transit",
        "by_neighborhood": p.by_neighborhood,
    }


# ---------- 2. plan the day ----------

@app.post("/api/plan")
async def plan(req: TripRequest):
    return StreamingResponse(plan_stream(req), media_type="application/x-ndjson")


async def plan_stream(req: TripRequest):
    msg = missing_keys_message()
    if msg:
        yield ev(type="error", message=msg)
        return
    trip = req.model_dump()
    city = trip["city"].strip()
    if not city:
        yield ev(type="error", message="Say which city you're visiting.")
        return
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            # --- find the starting point and candidate places
            start_q = f"{trip['start_location']}, {city}" if trip.get("start_location") else city
            yield step_run("find", "Find places worth seeing",
                           f'places.searchText("top tourist attractions in {city}")',
                           "server/places.py: search_text()")
            t0 = time.perf_counter()
            start_hits = await places.search_text(http, start_q, 1)
            if not start_hits:
                yield ev(type="error", message=f"Google Maps couldn't find “{start_q}”. Try a hotel name or street address.")
                return
            sp = start_hits[0]
            hotel = {"name": places.display_name(sp), "lat": sp["location"]["latitude"],
                     "lng": sp["location"]["longitude"]}
            utc_offset = sp.get("utcOffsetMinutes", 0)
            bias = (hotel["lat"], hotel["lng"])

            end_location = hotel
            if trip.get("end_location"):
                end_q = f"{trip['end_location']}, {city}"
                end_hits = await places.search_text(http, end_q, 1, bias)
                if not end_hits:
                    yield ev(type="error", message=(
                        f"Google Maps couldn't find “{end_q}”. "
                        "Try a station, airport, hotel, or street address."))
                    return
                ep = end_hits[0]
                end_location = {"name": places.display_name(ep), "lat": ep["location"]["latitude"],
                                "lng": ep["location"]["longitude"]}

            using_list = bool(trip["user_list"])
            queries = [] if using_list else (
                [f"top tourist attractions in {city}"] + [f"best {x} in {city}" for x in trip["loves"][:3]])
            named = ([(n, "must", None) for n in trip["must_see"]]
                     + [(n, "list", None) for n in trip["user_list"]]
                     + [(a["place"], "appointment", a["time"]) for a in trip["appointments"]])
            results = await asyncio.gather(
                *(places.search_text(http, q, 20, bias) for q in queries),
                *(places.search_text(http, f"{n}, {city}", 1, bias) for n, _, _ in named))
            found: dict[str, dict] = {}
            flags: dict[str, set] = {}
            appointment_times: dict[str, int] = {}
            rank: dict[str, int] = {}
            for qi, res in enumerate(results[:len(queries)]):
                for i, p in enumerate(res):
                    if qi == 0:
                        rank.setdefault(p["id"], i)
                    if places.is_visitable(p):
                        found.setdefault(p["id"], p)
            missing_names = []
            for (name, kind, appointment_time), res in zip(named, results[len(queries):]):
                if res:
                    pid = res[0]["id"]
                    found.setdefault(pid, res[0])
                    flags.setdefault(pid, set()).add(kind)
                    if appointment_time is not None:
                        minute = to_min(appointment_time, -1)
                        if minute >= 0:
                            appointment_times[pid] = minute
                else:
                    missing_names.append(name)
            ids = list(found)[:MAX_CANDIDATES]
            for pid in flags:  # never drop named places
                if pid not in ids:
                    ids.append(pid)
            raw = [found[i] for i in ids]
            if not raw:
                yield ev(type="error", message=f"No places came back for {city}. Check the city name.")
                return
            res_txt = (f"Matched {len(raw)} places from your list" if using_list
                       else f"{len(raw)} places from {len(queries)} searches, each with location and hours")
            if missing_names:
                res_txt += f". Couldn't find: {', '.join(missing_names)}"
            yield step_ok("find", t0, res_txt + ".")

            # --- Gemini scores every candidate for this traveler
            yield step_run("score", "Score each place for you",
                           f"gemini.generate_content({len(raw)} places + your preferences)",
                           "server/gemini.py: score_places()")
            t0 = time.perf_counter()
            brief = [{"id": p["id"], "name": places.display_name(p), "types": p.get("types", [])[:4],
                      "rating": p.get("rating"), "reviews": p.get("userRatingCount", 0),
                      "summary": p.get("editorialSummary", {}).get("text", ""),
                      "must_see": "must" in flags.get(p["id"], set()),
                      "appointment": "appointment" in flags.get(p["id"], set())} for p in raw]
            judged = {j.id: j for j in await gemini.score_places(
                {k: trip[k] for k in ("city", "loves", "skips", "must_see", "appointments", "pace")}, brief)}
            cands = []
            for p in raw:
                j = judged.get(p["id"])
                must = "must" in flags.get(p["id"], set())
                c = planner.Cand(
                    id=p["id"], name=places.display_name(p),
                    lat=p["location"]["latitude"], lng=p["location"]["longitude"],
                    rating=p.get("rating"), count=p.get("userRatingCount", 0),
                    maps_uri=p.get("googleMapsUri", ""), address=p.get("formattedAddress", ""),
                    list_rank=rank.get(p["id"], 999), hood=places.neighborhood(p),
                    score=max(0, min(100, j.score)) if j else 30,
                    kind=j.kind if j and j.kind in planner.KIND_DEFAULT_MIN else "sight",
                    setting=j.setting if j and j.setting in planner.RAIN_FACTOR else "indoor",
                    reason=j.reason if j else "", must=must,
                    appointment_time=appointment_times.get(p["id"]))
                c.visit_min = planner.KIND_DEFAULT_MIN[c.kind]
                c._raw = p
                if c.score > 0 or must or c.appointment_time is not None or using_list:
                    cands.append(c)
            cands.sort(key=lambda c: (not (c.must or c.appointment_time is not None), -c.score))
            required = sum(c.must or c.appointment_time is not None for c in cands)
            shortlist = cands[:max(SHORTLIST, required)]
            top = ", ".join(f"{c.name} {c.score}" for c in shortlist[:3])
            log.info("Trip %s: loves=%s skips=%s must_see=%s", city, trip["loves"], trip["skips"], trip["must_see"])
            short_ids = {c.id for c in shortlist}
            log.info("Scored places (* = shortlisted for the solver):\n%s", "\n".join(
                f"  {'*' if c.id in short_ids else ' '} {c.score:3d} {c.kind:<9} {c.name} | must={c.must} | {c.reason}"
                for c in cands))
            yield step_ok("score", t0, f"Kept the best {len(shortlist)} for you. Top matches: {top}.")

            # --- reviews -> visit lengths
            yield step_run("reviews", "Read reviews for visit lengths",
                           f'places.get(fields="reviews") x {len(shortlist)}, then gemini -> VisitEstimate',
                           "server/places.py: get_reviews(), server/gemini.py: estimate_visits()")
            t0 = time.perf_counter()
            revs = await asyncio.gather(*(places.get_reviews(http, c.id) for c in shortlist),
                                        return_exceptions=True)
            revs = [r if isinstance(r, list) else [] for r in revs]
            items = [{"id": c.id, "name": c.name, "kind": c.kind,
                      "reviews": [f"{i + 1}. {r['text'][:700]}" for i, r in enumerate(rv)]}
                     for c, rv in zip(shortlist, revs)]
            try:
                est = {e.id: e for e in await gemini.estimate_visits(trip, items)}
            except Exception:  # noqa: BLE001  (fall back to typical lengths)
                est = {}
            n_rev = 0
            for c, rv in zip(shortlist, revs):
                e = est.get(c.id)
                if not e:
                    c.visit_source = "default"
                    continue
                c.visit_min = max(15, min(180, int(e.minutes)))
                if e.from_reviews and e.evidence:
                    n_rev += 1
                    c.visit_source = "reviews"
                    for qi, quote in enumerate(e.evidence[:3]):
                        num = e.review_numbers[qi] if qi < len(e.review_numbers) else 0
                        r = rv[num - 1] if 1 <= num <= len(rv) else None
                        c.evidence.append({"quote": quote, "author": r["author"] if r else "A Google user",
                                           "uri": r["uri"] if r else ""})
                    c.evidence.append({"of": len(rv)})
                else:
                    c.visit_source = "gemini"
            yield step_ok("reviews", t0,
                          f"{n_rev} of {len(shortlist)} places have reviews that say how long to stay. "
                          "The rest use Gemini's own estimate.")

            # --- hours, neighborhoods, sunset (no API calls)
            yield step_run("hours", "Check hours and neighborhoods", "opening_windows(), assign_zones()",
                           "server/places.py, server/planner.py")
            t0 = time.perf_counter()
            local_now = datetime.now(timezone.utc) + timedelta(minutes=utc_offset)
            try:
                day = Date.fromisoformat(trip["date"]) if trip.get("date") else local_now.date()
            except ValueError:
                day = local_now.date()
            weekday = (day.weekday() + 1) % 7   # Places API: 0 = Sunday
            closed = 0
            for c in shortlist:
                c.windows, c.hours_known = places.opening_windows(c._raw, weekday)
                closed += not c.windows
            planner.assign_zones(shortlist)
            sunset = planner.sunset_minutes(hotel["lat"], hotel["lng"], day, utc_offset)
            zones = sorted({c.zone_name for c in shortlist})
            yield step_ok("hours", t0,
                          f"{closed} closed on {day.strftime('%A')}. {len(zones)} neighborhoods. "
                          f"Sunset around {fmt(sunset) if sunset else 'n/a'}.")

            # --- hourly forecast
            start_min = to_min(trip["start_time"], 600)
            deadline = to_min(trip["end_time"], 1140)
            if deadline <= start_min:
                deadline = min(1439, start_min + 60)
            yield step_run("weather", "Check the hourly forecast",
                           f"weather.forecast.hours.lookup(hotel location, through {day.isoformat()})",
                           "server/weather.py: hourly()")
            t0 = time.perf_counter()
            wx_error = None
            try:
                forecast = await weather.hourly(http, hotel["lat"], hotel["lng"], day, utc_offset)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.warning("Weather forecast unavailable: %s", e)
                forecast, wx_error = [], e
            rain_hours = weather.rain_hours(forecast)
            rain = _rain_windows(rain_hours, start_min, deadline)
            if wx_error is not None:
                wx_txt = ("Couldn't get the forecast (check that the Weather API is enabled for the "
                          "Maps key), so the plan assumes it stays dry.")
            elif not forecast:
                wx_txt = ("No forecast for that date (it covers the next 10 days), "
                          "so the plan assumes it stays dry.")
            elif rain:
                wx_txt = f"Rain likely {_windows_text(rain)}. Outdoor stops go to the dry hours."
            else:
                wx_txt = f"No rain expected between {fmt(start_min)} and {fmt(deadline)}."
            wx_detail = "\n".join(f"{fmt(x['hour'] * 60):>8}  {x['prob']:3d}%  {x['mm']:.1f} mm"
                                   for x in forecast if start_min // 60 <= x["hour"] <= deadline // 60)
            yield step_ok("weather", t0, wx_txt, wx_detail or None)

            # --- travel times
            pts = [(hotel["lat"], hotel["lng"])] + [(c.lat, c.lng) for c in shortlist]
            end_node = 0
            if trip.get("end_location"):
                end_node = len(pts)
                pts.append((end_location["lat"], end_location["lng"]))
            modes = ["WALK", "TRANSIT"] + (["DRIVE"] if trip["getting_around"] == "ride" else [])
            yield step_run("matrix", "Get travel times between every pair",
                           f"routes.computeRouteMatrix({len(pts)} x {len(pts)}, {', '.join(modes)})",
                           "server/routes.py: matrix()")
            t0 = time.perf_counter()
            dep_local = datetime.combine(day, datetime.min.time()) + timedelta(minutes=start_min)
            dep_utc = dep_local - timedelta(minutes=utc_offset)
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            if dep_utc < now_utc + timedelta(minutes=2):
                dep_utc = now_utc + timedelta(minutes=5)
            dep_iso = dep_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            mats = await asyncio.gather(*(routes.matrix(http, pts, m, dep_iso) for m in modes))
            walk, walk_m = mats[0]
            transit = mats[1][0]
            drive = mats[2][0] if len(mats) > 2 else None
            yield step_ok("matrix", t0, f"{len(pts) ** 2 * len(modes):,} real travel times "
                                        f"({', '.join(m.lower() for m in modes)}).")

            s = planner.Session(
                id=uuid.uuid4().hex[:12], trip=trip, date=day.isoformat(), weekday=weekday,
                utc_offset=utc_offset, sunset=sunset, hotel=hotel,
                end_location=end_location, end_node=end_node, cands=shortlist,
                walk=walk, walk_m=walk_m, transit=transit, drive=drive,
                start=start_min, deadline=deadline, now=start_min, loc=0,
                forecast=forecast, rain_hours=rain_hours)
            for c in shortlist:
                del c._raw

            # --- OR-Tools
            yield step_run("solve", "Choose the stops and their order",
                           "OR-Tools routing: time windows, optional stops"
                           + (", neighborhood switch cost" if s.blocks else ""),
                           "server/planner.py: solve()")
            t0 = time.perf_counter()
            nodes = list(range(1, len(shortlist) + 1))
            s.route = await asyncio.to_thread(planner.solve, s, s.now, 0, nodes)
            s.initial_route, s.initial_meal_slot = list(s.route), dict(s.meal_slot)
            s.initial_weather_slot = dict(s.weather_slot)
            base = planner.naive(s, s.now, 0, nodes)
            res = planner.simulate(s, s.route, s.now, 0)
            nres = planner.simulate(s, base, s.now, 0)
            s.compare = {"window": deadline - start_min,
                         "plan": _stats(res), "naive": _stats(nres)}
            blocks_txt = ""
            if s.blocks and res and res["stops"]:
                nb = len(_blocks(s, res["stops"]))
                blocks_txt = f" Grouped into {nb} neighborhood block{'s' if nb > 1 else ''}."
            yield step_ok("solve", t0, f"Picked {len(s.route)} of {len(nodes)} places.{blocks_txt}")
            remember_session(s)

            yield step_run("shapes", "Draw the real routes", "routes.computeRoutes(each leg)",
                           "server/routes.py: polyline()")
            t0 = time.perf_counter()
            await _fetch_polylines(http, s)
            yield step_ok("shapes", t0, "Street and transit shapes for each leg.")

            yield step_run("narrate", "Explain the plan", "gemini.generate_content(itinerary)",
                           "server/gemini.py: narrate_plan()")
            t0 = time.perf_counter()
            cuts = planner.cut_reasons(s, nodes, s.route, s.now)
            story = await _story(s, cuts)
            yield step_ok("narrate", t0, "Wrote the summary above the map.")
            yield ev(type="plan", **_payload(s, story, cuts))
    except Exception as e:  # noqa: BLE001
        yield ev(type="error", message=explain_error(e))


# ---------- 3. live changes ----------

@app.post("/api/interpret")
async def interpret(req: InterpretRequest):
    s = get_session(req.session_id)
    if not s:
        raise HTTPException(404, "That plan has expired. Plan the day again.")
    nxt = s.cand(s.route[0]).name if s.route else None
    ctx = {"time": fmt(s.now), "next_stop": nxt, "raining": s.raining, "tired": s.tired}
    try:
        return await gemini.interpret_event(req.text, ctx)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gemini couldn't interpret that: {e}")


@app.post("/api/replan")
async def replan(req: ReplanRequest):
    return StreamingResponse(replan_stream(req), media_type="application/x-ndjson")


async def replan_stream(req: ReplanRequest):
    s = get_session(req.session_id)
    if not s:
        yield ev(type="error", message="That plan has expired. Plan the day again.")
        return
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            nodes = [k for k in range(1, len(s.cands) + 1)
                     if k not in {x["node"] for x in s.completed} and k not in s.skipped]
            if req.event == "reset":
                s.completed, s.skipped, s.now, s.loc = [], set(), s.start, 0
                s.tired = False
                s.rain_hours = weather.rain_hours(s.forecast)
                s.route, s.changed, s.dropped = list(s.initial_route), set(), []
                s.locked = set()
                s.meal_slot = dict(s.initial_meal_slot)
                s.weather_slot = dict(s.initial_weather_slot)
                all_nodes = list(range(1, len(s.cands) + 1))
                cuts = planner.cut_reasons(s, all_nodes, s.route, s.now)
                yield ev(type="plan", **_payload(s, "Back to the start of the day. " + await _story(s, cuts), cuts))
                return
            node = next((k for k, c in enumerate(s.cands, 1) if c.id == req.place_id), None)
            if req.event in ("include", "lock", "unlock") and node is None:
                yield ev(type="error", message="That place isn't part of this plan.")
                return
            if req.event in ("lock", "unlock"):
                name = s.cand(node).name
                if req.event == "lock":
                    s.locked.add(node)
                    story = f"Locked {name}. It will stay in the plan through later changes."
                else:
                    s.locked.discard(node)
                    story = f"Unlocked {name}. A later re-plan may drop it if something else fits better."
                s.changed, s.dropped = set(), []
                yield ev(type="step", key=req.event, status="ok", title="Nothing to re-plan",
                         result=story, fresh=True)
                yield ev(type="plan", **_payload(s, story, planner.cut_reasons(s, nodes, s.route, s.now)))
                return
            if req.event == "done":
                res = planner.simulate(s, s.route, s.now, s.loc)
                if not res or not res["stops"]:
                    yield ev(type="error", message="There's no next stop to finish.")
                    return
                st = res["stops"][0]
                s.completed.append(st)
                s.now, s.loc, s.route = st["leave"], st["node"], s.route[1:]
                s.changed, s.dropped = set(), []
                nodes = [k for k in nodes if k != st["node"]]
                nxt = planner.simulate(s, s.route, s.now, s.loc)
                if s.route and nxt:
                    first = nxt["stops"][0]
                    story = (f"Done with {s.cand(st['node']).name}. Next up is {s.cand(first['node']).name}, "
                             f"arriving around {fmt(first['arrive'])}.")
                else:
                    s.route = []
                    story = (f"Done with {s.cand(st['node']).name}. That was the last stop, "
                             f"so head to {s.end_location['name']}.")
                yield ev(type="step", key="done", status="ok", title="Nothing to re-plan",
                         result=f"You finished on schedule. The clock moved to {fmt(s.now)}.", fresh=True)
                yield ev(type="plan", **_payload(s, story, planner.cut_reasons(s, nodes, s.route, s.now)))
                return

            prev = list(s.route)
            prev_next = prev[0] if prev else None
            if req.event == "late":
                s.now += max(1, req.delay_minutes)
            elif req.event == "rain":
                s.rain_hours |= set(range(s.now // 60, 24))  # it's raining now; assume it keeps up
            elif req.event == "tired":
                s.tired = True
            elif req.event == "skip" and prev_next:
                s.skipped.add(prev_next)
                nodes = [k for k in nodes if k != prev_next]
            elif req.event == "include":
                s.locked.add(node)
                s.skipped.discard(node)
                if node not in nodes:
                    nodes.append(node)
            else:
                yield ev(type="error", message=f"Unknown event: {req.event}")
                return

            yield step_run("resolve", "Re-plan the rest of the day",
                           f"OR-Tools from {fmt(s.now)}, {len(nodes)} places left",
                           "server/planner.py: solve()")
            t0 = time.perf_counter()
            s.route = await asyncio.to_thread(planner.solve, s, s.now, s.loc, nodes)
            s.changed = set(s.route) - set(prev)
            could_not_fit = None
            if req.event == "include" and node not in s.route:
                s.locked.discard(node)  # forcing couldn't make it fit, so don't leave it locked
                could_not_fit = s.cand(node).name
            s.dropped = [s.cand(k).name for k in prev
                         if k not in s.route and not (req.event == "skip" and k == prev_next)]
            yield step_ok("resolve", t0, f"{len(s.route)} stops still fit. Travel times came from the cached matrix.",
                          )
            yield step_run("shapes", "Draw the new routes", "routes.computeRoutes(new legs)",
                           "server/routes.py: polyline()")
            t0 = time.perf_counter()
            await _fetch_polylines(http, s)
            yield step_ok("shapes", t0, "Updated leg shapes.")
            yield step_run("narrate", "Explain the change", "gemini.generate_content(old plan, new plan)",
                           "server/gemini.py: narrate_change()")
            t0 = time.perf_counter()
            res = planner.simulate(s, s.route, s.now, s.loc)
            facts = {"event": req.event, "time_now": fmt(s.now),
                     "dropped": s.dropped, "added": [s.cand(k).name for k in s.changed],
                     "skipped": s.cand(prev_next).name if req.event == "skip" and prev_next else None,
                     "put_back": s.cand(node).name if req.event == "include" and not could_not_fit else None,
                     "could_not_fit": could_not_fit,
                     "next": (s.cand(res["stops"][0]["node"]).name + " at " + fmt(res["stops"][0]["arrive"]))
                     if res and res["stops"] else None,
                     "finish_by": fmt(res["end"]) if res else None,
                     "finish_at": s.end_location["name"]}
            try:
                story = await gemini.narrate_change(facts)
            except Exception:  # noqa: BLE001
                story = _fallback_change(facts)
            yield step_ok("narrate", t0, "Wrote what changed and why.")
            yield ev(type="plan", **_payload(s, story, planner.cut_reasons(s, nodes, s.route, s.now)))
    except Exception as e:  # noqa: BLE001
        yield ev(type="error", message=explain_error(e))


# ---------- building the response ----------

def _stats(res):
    if not res:
        return None
    return {"stops": len(res["stops"]), "see": res["see"], "travel": res["travel"], "waited": res["waited"]}


def _rain_windows(rain_hours, start, end):
    """Rainy spells clipped to the trip window, as [from, to] minutes."""
    return [[max(a, start), min(b, end)] for a, b in planner.spells(rain_hours) if b > start and a < end]


def _windows_text(windows):
    return ", ".join(f"{fmt(a)} to {fmt(b)}" for a, b in windows)


def _blocks(s, stops):
    out = []
    for st in stops:
        z = s.cand(st["node"]).zone_name
        if out and out[-1]["zone"] == z:
            out[-1]["to"], out[-1]["count"] = st["leave"], out[-1]["count"] + 1
        else:
            out.append({"zone": z, "from": st["begin"], "to": st["leave"], "count": 1})
    return out


async def _fetch_polylines(http, s):
    res = planner.simulate(s, s.route, s.now, s.loc)
    if not res:
        return
    legs = [(st["from"], st["node"], st["leg"]["mode"]) for st in res["stops"]]
    legs.append((res["back"]["from"], s.end_node, res["back"]["mode"]))
    todo = [k for k in legs if k not in s.polylines and k[0] != k[1]]
    got = await asyncio.gather(*(routes.polyline(http, s.point(a), s.point(b), MODE_API[m]) for a, b, m in todo),
                               return_exceptions=True)
    for k, g in zip(todo, got):
        if isinstance(g, str):
            s.polylines[k] = g


async def _story(s, cuts):
    res = planner.simulate(s, s.route, s.now, s.loc)
    if not res or not res["stops"]:
        return (f"There isn't time for a stop and still reaching {s.end_location['name']} "
                f"by {fmt(s.deadline)}. "
                "Try a later end time or a closer starting point.")
    facts = {
        "window": f"{fmt(s.start)} to {fmt(s.deadline)}",
        "stops": [{"name": s.cand(x["node"]).name, "at": fmt(x["begin"]),
                   "neighborhood": s.cand(x["node"]).zone_name, "notes": x["notes"]} for x in res["stops"]],
        "neighborhood_blocks": [b["zone"] for b in _blocks(s, res["stops"])] if s.blocks else [],
        "walking_km": res["walk_km"], "sunset": fmt(s.sunset) if s.sunset else None,
        "rain_forecast": _windows_text(_rain_windows(s.rain_hours, s.start, s.deadline)) or None,
        "left_out": cuts[:2],
        "finish": {"name": s.end_location["name"], "at": fmt(res["end"])},
        "traveler": {k: s.trip.get(k) for k in ("loves", "skips", "pace")},
    }
    try:
        return await gemini.narrate_plan(facts)
    except Exception:  # noqa: BLE001
        first = facts["stops"][0]
        return (f"{len(facts['stops'])} stops between {facts['window']}, starting at {first['name']} "
                f"at {first['at']}. You'll finish at {facts['finish']['name']} by {facts['finish']['at']}.")


def _fallback_change(f):
    out = []
    if f.get("could_not_fit"):
        out.append(f"Couldn't fit {f['could_not_fit']} back in, even after moving things around.")
    if f.get("put_back"):
        out.append(f"Put {f['put_back']} back in the plan.")
    if f["dropped"]:
        out.append(f"Dropped {', '.join(f['dropped'])}.")
    added = [x for x in f["added"] if x != f.get("put_back")]
    if added:
        out.append(f"Added {', '.join(added)}.")
    if f["next"]:
        out.append(f"Next up: {f['next']}.")
    if f["finish_by"]:
        out.append(f"Finish at {f['finish_at']} by {f['finish_by']}.")
    return " ".join(out) or "The plan still works as is."


def _log_itinerary(s, res):
    lines = [f"Itinerary {s.id} ({s.trip['city']} {s.date}, now {fmt(s.now)}, deadline {fmt(s.deadline)}):"]
    for label, stops in (("done", s.completed), ("next", res["stops"])):
        for st in stops:
            c = s.cand(st["node"])
            lines.append(f"  [{label}] {fmt(st['begin'])}-{fmt(st['leave'])} {c.name} | kind={c.kind} score={c.score} "
                         f"must={c.must} zone={c.zone_name} notes={st['notes']} "
                         f"leg={st['leg']['mode']} {st['leg']['min']}min | {c.reason}")
    lines.append(f"  at {s.end_location['name']} by {fmt(res['end'])}")
    log.info("\n".join(lines))


def _stop_json(s, st, done):
    c = s.cand(st["node"])
    L = dict(st["leg"])
    L["polyline"] = s.polylines.get((st["from"], st["node"], L["mode"]))
    return {"id": c.id, "name": c.name, "lat": c.lat, "lng": c.lng,
            "arrive": st["arrive"], "begin": st["begin"], "wait": st["wait"], "leave": st["leave"],
            "leg": L, "notes": st["notes"], "done": done, "new": (not done) and st["node"] in s.changed,
            "visit": {"minutes": st["leave"] - st["begin"], "base": c.visit_min,
                      "source": c.visit_source, "evidence": c.evidence},
            "zone": c.zone_name, "kind": c.kind, "setting": c.setting, "reason": c.reason,
            "rating": c.rating, "count": c.count, "maps_uri": c.maps_uri,
            "hours_known": c.hours_known,
            "locked": c.must or c.appointment_time is not None or st["node"] in s.locked, "must": c.must,
            "fixed": c.appointment_time is not None,
            "opens": c.windows[0][0] if c.windows else None}


def _payload(s, story, cuts):
    res = planner.simulate(s, s.route, s.now, s.loc)
    if res is None:  # out of time: go straight to the end point
        back = planner.leg(s, s.loc, s.end_node)
        res = {"stops": [], "back": {**back, "from": s.loc}, "end": s.now + back["min"],
               "travel": back["min"], "walk_km": back["km"] if back["mode"] == "walk" else 0}
        s.route = []
    _log_itinerary(s, res)
    back = dict(res["back"])
    back["polyline"] = s.polylines.get((back["from"], s.end_node, back["mode"]))
    back.pop("from", None)
    done = [_stop_json(s, st, True) for st in s.completed]
    upcoming = [_stop_json(s, st, False) for st in res["stops"]]
    all_stops = s.completed + res["stops"]
    in_plan = {x["node"] for x in all_stops}
    walk = sum(x["leg"]["km"] for x in all_stops if x["leg"]["mode"] == "walk") + \
        (back["km"] if back["mode"] == "walk" else 0)
    return {
        "session_id": s.id, "city": s.trip["city"], "date": s.date,
        "start": s.start, "deadline": s.deadline, "now": s.now, "sunset": s.sunset,
        "raining": s.raining, "tired": s.tired, "trip": s.trip,
        "forecast": bool(s.forecast), "rain": _rain_windows(s.rain_hours, s.start, s.deadline),
        "hotel": s.hotel, "end_location": s.end_location,
        "at": s.hotel["name"] if s.loc == 0 else s.cand(s.loc).name,
        "shifted": bool(s.completed and s.now != s.completed[-1]["leave"]) or (not s.completed and s.now != s.start),
        "completed": done, "stops": upcoming, "back": back, "end": res["end"],
        "blocks": _blocks(s, all_stops) if s.blocks else [],
        "summary": {"stops": len(all_stops), "walk_km": round(walk, 1),
                    "moving": sum(x["leg"]["min"] for x in all_stops) + back["min"],
                    "zones": len({s.cand(x["node"]).zone_name for x in all_stops})},
        "others": [{"name": c.name, "lat": c.lat, "lng": c.lng}
                   for k, c in enumerate(s.cands, 1) if k not in in_plan],
        "cuts": cuts, "dropped": s.dropped, "story": story,
        "compare": getattr(s, "compare", None),
    }
