"""Sightline API server.

Run from the project root:
    uvicorn server.main:app --reload
then open http://localhost:8000

/api/plan and /api/replan stream newline-delimited JSON: "step" events as each
stage runs (for the agent trace), then one "plan" event, or an "error" event.
"""
import asyncio
import json
import time
import uuid
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from . import config, gemini, places, planner, routes
from .models import InterpretRequest, ParseRequest, ReplanRequest, TripRequest

app = FastAPI(title="Sightline")
WEB = Path(__file__).resolve().parent.parent / "web"
SESSIONS: dict[str, planner.Session] = {}   # in memory, one per planned day
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


def place_json(place: dict) -> dict:
    return {"name": places.display_name(place), "lat": place["location"]["latitude"],
            "lng": place["location"]["longitude"]}


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


# ---------- pages & config ----------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def get_config():
    return {"mapsKey": config.MAPS_BROWSER_KEY, "mapId": config.MAP_ID,
            "missing": config.missing_keys(), "model": config.GEMINI_MODEL}


# ---------- 1. understand the message ----------

@app.post("/api/parse")
async def parse(req: ParseRequest):
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Add GEMINI_API_KEY to the .env file, then restart the server.")
    try:
        p = await gemini.parse_trip(req.message, Date.today().isoformat())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gemini couldn't read the message: {e}")
    return {
        "city": p.city,
        "date": p.date or None,
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
            hotel = place_json(sp)
            end_place = hotel
            if trip.get("end_location"):
                end_q = f"{trip['end_location']}, {city}"
                end_hits = await places.search_text(http, end_q, 1)
                if not end_hits:
                    yield ev(type="error", message=f"Google Maps couldn't find “{end_q}”. Try a station, airport or street address.")
                    return
                end_place = place_json(end_hits[0])
            utc_offset = sp.get("utcOffsetMinutes", 0)
            bias = (hotel["lat"], hotel["lng"])

            using_list = bool(trip["user_list"])
            appointments = []
            for appt in trip.get("appointments", []):
                place = (appt.get("place") or "").strip()
                fixed = to_min(appt.get("time"), -1)
                if not place or fixed < 0:
                    continue
                appointments.append({
                    "place": place,
                    "time_min": fixed,
                    "duration_minutes": max(15, min(240, int(appt.get("duration_minutes") or 60))),
                })
            queries = [] if using_list else (
                [f"top tourist attractions in {city}"] + [f"best {x} in {city}" for x in trip["loves"][:3]])
            named = ([(n, "must") for n in trip["must_see"]]
                     + [(a["place"], "appointment") for a in appointments]
                     + [(n, "list") for n in trip["user_list"]])
            results = await asyncio.gather(
                *(places.search_text(http, q, 20, bias) for q in queries),
                *(places.search_text(http, f"{n}, {city}", 1, bias) for n, _ in named))
            found: dict[str, dict] = {}
            flags: dict[str, set] = {}
            fixed_by_id: dict[str, dict] = {}
            rank: dict[str, int] = {}
            for qi, res in enumerate(results[:len(queries)]):
                for i, p in enumerate(res):
                    if qi == 0:
                        rank.setdefault(p["id"], i)
                    if places.is_visitable(p):
                        found.setdefault(p["id"], p)
            missing_names = []
            appt_by_name = {a["place"]: a for a in appointments}
            for (name, kind), res in zip(named, results[len(queries):]):
                if res:
                    found.setdefault(res[0]["id"], res[0])
                    flags.setdefault(res[0]["id"], set()).add(kind)
                    if kind == "appointment":
                        fixed_by_id.setdefault(res[0]["id"], appt_by_name[name])
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
                      "must_see": bool(flags.get(p["id"], set()) & {"must", "appointment"})} for p in raw]
            judged = {j.id: j for j in await gemini.score_places(
                {k: trip[k] for k in ("city", "loves", "skips", "must_see", "appointments", "pace")}, brief)}
            cands = []
            for p in raw:
                j = judged.get(p["id"])
                fixed = fixed_by_id.get(p["id"])
                must = "must" in flags.get(p["id"], set()) or fixed is not None
                c = planner.Cand(
                    id=p["id"], name=places.display_name(p),
                    lat=p["location"]["latitude"], lng=p["location"]["longitude"],
                    rating=p.get("rating"), count=p.get("userRatingCount", 0),
                    maps_uri=p.get("googleMapsUri", ""), address=p.get("formattedAddress", ""),
                    list_rank=rank.get(p["id"], 999), hood=places.neighborhood(p),
                    score=max(0, min(100, j.score)) if j else 30,
                    kind=j.kind if j and j.kind in planner.KIND_DEFAULT_MIN else "sight",
                    setting=j.setting if j and j.setting in planner.RAIN_FACTOR else "indoor",
                    reason=j.reason if j else "", must=must)
                c.visit_min = planner.KIND_DEFAULT_MIN[c.kind]
                if fixed:
                    c.fixed_time = fixed["time_min"]
                    c.visit_min = fixed["duration_minutes"]
                    c.appointment_label = f"Fixed at {fmt(c.fixed_time)}"
                    c.reason = c.reason or c.appointment_label
                c._raw = p
                if c.score > 0 or must or using_list:
                    cands.append(c)
            cands.sort(key=lambda c: (not c.must, -c.score))
            shortlist = cands[:max(SHORTLIST, sum(c.must for c in cands))]
            top = ", ".join(f"{c.name} {c.score}" for c in shortlist[:3])
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

            # --- travel times
            start_min = to_min(trip["start_time"], 600)
            deadline = to_min(trip["end_time"], 1140)
            if deadline <= start_min:
                deadline = min(1439, start_min + 60)
            pts = ([(hotel["lat"], hotel["lng"])] + [(c.lat, c.lng) for c in shortlist]
                   + [(end_place["lat"], end_place["lng"])])
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
                utc_offset=utc_offset, sunset=sunset, hotel=hotel, end=end_place, cands=shortlist,
                walk=walk, walk_m=walk_m, transit=transit, drive=drive,
                start=start_min, deadline=deadline, now=start_min, loc=0)
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
            s.initial_route = list(s.route)
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
            SESSIONS[s.id] = s

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
    s = SESSIONS.get(req.session_id)
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
    s = SESSIONS.get(req.session_id)
    if not s:
        yield ev(type="error", message="That plan has expired. Plan the day again.")
        return
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            nodes = [k for k in range(1, len(s.cands) + 1)
                     if k not in {x["node"] for x in s.completed} and k not in s.skipped]
            if req.event == "reset":
                s.completed, s.skipped, s.now, s.loc = [], set(), s.start, 0
                s.raining = s.tired = False
                s.route, s.changed, s.dropped = list(s.initial_route), set(), []
                all_nodes = list(range(1, len(s.cands) + 1))
                cuts = planner.cut_reasons(s, all_nodes, s.route, s.now)
                yield ev(type="plan", **_payload(s, "Back to the start of the day. " + await _story(s, cuts), cuts))
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
                    story = f"Done with {s.cand(st['node']).name}. That was the last stop, so head to {s.end['name']}."
                yield ev(type="step", key="done", status="ok", title="Nothing to re-plan",
                         result=f"You finished on schedule. The clock moved to {fmt(s.now)}.", fresh=True)
                yield ev(type="plan", **_payload(s, story, planner.cut_reasons(s, nodes, s.route, s.now)))
                return

            prev = list(s.route)
            prev_next = prev[0] if prev else None
            if req.event == "late":
                s.now += max(1, req.delay_minutes)
            elif req.event == "rain":
                s.raining = True
            elif req.event == "tired":
                s.tired = True
            elif req.event == "skip" and prev_next:
                s.skipped.add(prev_next)
                nodes = [k for k in nodes if k != prev_next]
            else:
                yield ev(type="error", message=f"Unknown event: {req.event}")
                return

            yield step_run("resolve", "Re-plan the rest of the day",
                           f"OR-Tools from {fmt(s.now)}, {len(nodes)} places left",
                           "server/planner.py: solve()")
            t0 = time.perf_counter()
            s.route = await asyncio.to_thread(planner.solve, s, s.now, s.loc, nodes)
            s.changed = set(s.route) - set(prev)
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
                     "next": (s.cand(res["stops"][0]["node"]).name + " at " + fmt(res["stops"][0]["arrive"]))
                     if res and res["stops"] else None,
                     "back_at_end": fmt(res["end"]) if res else None}
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
        return (f"There isn't time for a stop and still reaching {s.end['name']} by {fmt(s.deadline)}. "
                "Try a later end time or a closer starting point.")
    facts = {
        "window": f"{fmt(s.start)} to {fmt(s.deadline)}",
        "stops": [{"name": s.cand(x["node"]).name, "at": fmt(x["begin"]),
                   "neighborhood": s.cand(x["node"]).zone_name, "notes": x["notes"]} for x in res["stops"]],
        "neighborhood_blocks": [b["zone"] for b in _blocks(s, res["stops"])] if s.blocks else [],
        "walking_km": res["walk_km"], "sunset": fmt(s.sunset) if s.sunset else None,
        "left_out": cuts[:2], "finish_at": s.end["name"], "back_at_hotel": fmt(res["end"]),
        "traveler": {k: s.trip.get(k) for k in ("loves", "skips", "pace")},
    }
    try:
        return await gemini.narrate_plan(facts)
    except Exception:  # noqa: BLE001
        first = facts["stops"][0]
        return (f"{len(facts['stops'])} stops between {facts['window']}, starting at {first['name']} "
                f"at {first['at']}. You're back by {facts['back_at_hotel']}.")


def _fallback_change(f):
    out = []
    if f["dropped"]:
        out.append(f"Dropped {', '.join(f['dropped'])}.")
    if f["added"]:
        out.append(f"Added {', '.join(f['added'])}.")
    if f["next"]:
        out.append(f"Next up: {f['next']}.")
    if f["back_at_end"]:
        out.append(f"Finish by {f['back_at_end']}.")
    return " ".join(out) or "The plan still works as is."


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
            "fixed_time": c.fixed_time, "appointment_label": c.appointment_label,
            "rating": c.rating, "count": c.count, "maps_uri": c.maps_uri,
            "hours_known": c.hours_known,
            "opens": c.windows[0][0] if c.windows else None}


def _payload(s, story, cuts):
    res = planner.simulate(s, s.route, s.now, s.loc)
    if res is None:  # out of time: just head back
        back = planner.leg(s, s.loc, s.end_node)
        res = {"stops": [], "back": {**back, "from": s.loc}, "end": s.now + back["min"],
               "travel": back["min"], "walk_km": back["km"] if back["mode"] == "walk" else 0}
        s.route = []
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
        "hotel": s.hotel, "end_place": s.end, "at": s.hotel["name"] if s.loc == 0 else s.cand(s.loc).name,
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
