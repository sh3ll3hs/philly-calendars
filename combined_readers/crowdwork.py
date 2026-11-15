"""
Crowdwork / FourthWall theatre shows, read from the public JSON the theatre's own
website embed loads: https://crowdwork.com/api/v2/<theatre>/shows (one request per run).

Used for SideQuest Theater (sidequesttheater.com/shows). The embed script describes this
endpoint as public, open to any origin, with no token; it answered a plain request on
2026-11-15. Crowdwork's event pages themselves sit behind a bot challenge and are never
requested: event links are passed through for the subscriber's own browser only.

Each show has `name`, `dates` (every performance, ISO with offset), `location`,
`description_short`, `url`, `status`. One calendar entry per performance.
"""
import combined_to_ics as C


def parse(data, src):
    out = []
    for show in data.get("data") or []:
        if str(show.get("status", "active")).lower() != "active":
            continue
        loc = C.clean(str(show.get("location") or "")).replace(" PA 19103, PA", ", PA 19103")
        if loc and src.get("venue") and src["venue"].lower() not in loc.lower():
            loc = f"{src['venue']}, {loc}"
        for when in show.get("dates") or []:
            st = C.parse_iso(when)
            if not st:
                continue
            e = C.event(src, f"{show.get('id')}|{when}", show.get("name"), st[0], None, st[1], loc,
                        show.get("url") or src.get("page") or "", show.get("description_short"))
            if e:
                out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_json(src["url"]), src)
