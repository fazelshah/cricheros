from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse
import requests
import json
import re
import time

import os

AUTH_COOKIE = os.environ["AUTH_COOKIE"]
API_HEADERS = {
    "Authorization": AUTH_COOKIE,
    "Api-Key": "cr!CkH3r0s",
    "Device-Type": "Chrome: 149.0.0.0",
    "Udid": "b0786f2371cee401832c4ef644142090",
    "Accept": "application/json",
    "user-agent": "Mozilla/5.0",
}

# Srinagar coordinates
LAT = "34.150690904977736"
LON = "74.8118695621732"

def search_player(name, page=1):
    ts = int(time.time() * 1000)
    search_name = name.replace("-", " ")
    url = f"https://api.cricheroes.in/api/v1/search/v2/global-search-all/2/{urllib.parse.quote(search_name)}?type=1&pagesize=9&pageno={page}&datetime={ts}"
    res = requests.get(url, headers=API_HEADERS)
    data = res.json()
    players = data.get("data", {}).get("players", [])
    has_next = bool(data.get("page", {}).get("next"))
    return players, has_next

def fetch_stats_by_id(player_id, player_name_slug):
    cookies = {"Authorization": AUTH_COOKIE}
    headers = {"rsc": "1", "user-agent": "Mozilla/5.0"}
    url = f"https://cricheroes.com/player-profile/{player_id}/{player_name_slug}?tab=matches"
    response = requests.get(url, cookies=cookies, headers=headers)
    text = response.text
    start = text.find('"playerInfo":')
    if start == -1:
        return None
    data_start = text.find('"data":{', start) + len('"data":')
    brace_count = 0
    end = data_start
    for i, ch in enumerate(text[data_start:], data_start):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    data = json.loads(text[data_start:end])
    statement = data.get("player_statement", "")
    def g(pattern):
        m = re.search(pattern, statement)
        return m.group(1) if m else "N/A"
    return {
        "player_id":    data.get("player_id"),
        "name":         data.get("name"),
        "city":         data.get("city_name"),
        "role":         data.get("playing_role"),
        "batting_hand": data.get("batting_hand"),
        "bowling_style":data.get("bowling_style"),
        "profile_photo":data.get("profile_photo"),
        "total_matches":data.get("total_matches"),
        "total_runs":   data.get("total_runs"),
        "total_wickets":data.get("total_wickets"),
        "batting_avg":  g(r'average of <b>([\d.]+)</b>'),
        "strike_rate":  g(r'strike rate of <b>([\d.]+)</b>'),
        "top_score":    g(r'top score of <b>([\d.]+)</b>'),
        "sixes":        g(r'<b>(\d+) sixes</b>'),
        "fours":        g(r'<b>(\d+) fours</b>'),
        "overs_bowled": g(r'bowled <b>([\d.]+)</b> overs'),
        "economy":      g(r'economy rate of <b>([\d.]+)</b>'),
    }

def fetch_live_matches(page=1):
    url = f"https://api.cricheroes.in/api/v1/search/v2/near-by-me-matches/{LAT}/{LON}?pagesize=20&pageno={page}"
    res = requests.get(url, headers=API_HEADERS)
    data = res.json()
    matches = data.get("data", [])
    has_next = bool(data.get("page", {}).get("next"))
    result = []
    for m in matches:
        result.append({
            "match_id":      m.get("match_id"),
            "status":        m.get("status"),
            "ground":        m.get("ground_name"),
            "city":          m.get("city_name"),
            "overs":         m.get("overs"),
            "date":          m.get("match_start_time", "")[:10],
            "tournament":    m.get("tournament_name", ""),
            "round":         m.get("tournament_round_name", ""),
            "team_a":        m.get("team_a"),
            "team_b":        m.get("team_b"),
            "team_a_score":  m.get("team_a_summary", ""),
            "team_b_score":  m.get("team_b_summary", ""),
            "summary":       m.get("match_summary", {}).get("summary", ""),
            "result":        m.get("match_result", ""),
            "winning_team":  m.get("winning_team", ""),
        })
    return result, has_next

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/search-player':
            name = params.get('name', [''])[0]
            page = int(params.get('page', ['1'])[0])
            try:
                players, has_next = search_player(name, page)
                if not players and page == 1:
                    raise Exception("No players found")
                result = {
                    "has_next": has_next,
                    "page": page,
                    "players": [
                        {
                            "user_id": p.get("user_id") or p.get("player_id"),
                            "name": p.get("name"),
                            "city": p.get("city_name", ""),
                            "photo": p.get("profile_photo", ""),
                            "slug": p.get("name","").lower().replace(" ", "-")
                        }
                        for p in players
                    ]
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif parsed.path == '/fetch-stats':
            player_id = params.get('id', [''])[0]
            player_name = params.get('name', [''])[0]
            stats = fetch_stats_by_id(player_id, player_name)
            if stats:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(stats).encode())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Player not found.')

        elif parsed.path == '/live-matches':
            page = int(params.get('page', ['1'])[0])
            try:
                matches, has_next = fetch_live_matches(page)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"matches": matches, "has_next": has_next}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass
import os

PORT = int(os.environ.get("PORT", 8000))

print(f"Server running on port {PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
