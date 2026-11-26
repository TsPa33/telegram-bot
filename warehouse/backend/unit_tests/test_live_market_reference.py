from decimal import Decimal
from html import escape
import pytest
from app.services import live_market_reference as live

STAMP = "2026-11-26T15:00:00+00:00"
CTX = dict(oem="8115006C41", name="Фара передня ліва у зборі",
           manufacturer="Toyota", model="Camry", year=2020, condition="used")
PATH = "/ua/n/81150-06c41/"
ROBOTS = "User-Agent: *\nDisallow: /ua/search/\nDisallow: /cart/\n"


def card(i, amount, *, oem="8115006C41", title="Фара передня ліва у зборі Toyota Camry 19-20",
         labels="Б/В", availability="В наявності", usd=""):
    return f'''<div class="detail-item">
    <div class="detail-item-title"><a href="/ua/detail/test-{i}/">{escape(title)}</a></div>
    <div class="detail-item-chars"><small>Арт. <b>{i}</b></small><small>Ориг. номер <b>{oem}</b></small></div>
    <div class="detail-item-uprice">{amount} грн</div>
    <div class="detail-item-price">{escape(usd)}</div>
    <div class="detail-item-labels">{escape(labels)}</div>
    <div>{escape(availability)}</div></div>'''


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(live, "_ATTEMPTS", [])
    monkeypatch.setattr(live, "_CACHE", live.OrderedDict())
    monkeypatch.setattr(live, "_ROBOTS", None)
    monkeypatch.setattr(live, "_LAST", float("-inf"))
    monkeypatch.delenv("WAREHOUSE_MARKET_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("WAREHOUSE_MARKET_ACCESS_MODE", raising=False)
    monkeypatch.delenv("WAREHOUSE_ENV", raising=False)


def authorize(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_MARKET_LIVE_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_MARKET_ACCESS_MODE", "limited_individual")
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")


def test_routes_and_fail_closed(monkeypatch):
    assert live.lookup_path(CTX) == PATH
    assert live.lookup_path(dict(CTX,oem="https://evil.test/")) is None
    assert live.lookup_path(dict(CTX,oem="../../private")) is None
    assert live.lookup_path(dict(CTX,oem="")) is None
    assert live.robots_allows(ROBOTS, PATH)
    assert not live.robots_allows(ROBOTS, "/ua/search/")
    assert not live.robots_allows("User-Agent: *\nDisallow: /ua/n/", PATH)
    assert not live.robots_allows("User-Agent: Bot\nDisallow: /", PATH)
    monkeypatch.setattr(live, "fetch_text", lambda *a: pytest.fail("unexpected network"))
    assert live.lookup(CTX)[0]=="disabled"
    monkeypatch.setenv("WAREHOUSE_MARKET_LIVE_ENABLED", "true")
    assert live.lookup(CTX)[0]=="disabled"


def test_parser_average_and_conflicts():
    html = "".join([card(1,1000),card(2,1500),card(3,2000,usd="invalid optional currency"),
        card(2,1500),card(4,99999,oem="WRONG123"),card(5,9000,availability="Очікується"),
        card(6,8000,availability="Немає в наявності"),
        card(7,9000,title="Фара передня права у зборі Toyota Camry 19-20"),
        card(8,8000,title="Корпус фари передньої лівої Toyota Camry 19-20"),
        card(9,7000,title="Фара передня ліва у зборі Toyota Camry 21-24"),
        card(10,6000,labels="Новий аналог"),card(11,5000,availability=""),
        card(12,9000),card(12,10000)])
    rows = live.parse_cards(html,PATH,STAMP)
    assert not any(r["article"]=="12" for r in rows)
    groups = live.references(CTX,rows)
    result = next(r for r in groups if r["condition"]=="used" and r["availability"]=="available")
    assert result["offer_count"]==3
    assert Decimal(result["average"])==1500 and Decimal(result["minimum"])==1000
    assert Decimal(result["maximum"])==2000
    assert all(set(e)=={"amount","currency","observed_at","url"} for e in result["examples"])
    assert all(r["average"] is None for r in groups if r is not result)
    assert not any(r["availability"] in ("expected","unavailable") for r in groups)


def test_cache_no_tenant_data_and_no_retry(monkeypatch):
    authorize(monkeypatch)
    calls=[]
    def fetch(path,limit=live.MAX_BYTES):
        calls.append(path)
        return ROBOTS if path=="/robots.txt" else "".join(card(i,1000*i) for i in range(1,4))
    monkeypatch.setattr(live,"fetch_text",fetch)
    first = live.lookup(CTX)
    assert first[0]=="live" and first[1][0]["average"]=="2000.00"
    cached = live.lookup(CTX)
    assert cached[0]=="cached" and cached[2]==first[2]
    assert calls==["/robots.txt",PATH]
    assert live.lookup(dict(CTX,model="Other"))[1]==[]
    assert calls==["/robots.txt",PATH]
    assert live.lookup(dict(CTX,oem="OTHER123"))[0]=="cooldown"


def test_blocked_robots_and_failed_source(monkeypatch):
    authorize(monkeypatch)
    calls=[]
    def blocked(path,limit=live.MAX_BYTES):
        calls.append(path)
        return "User-Agent: *\nDisallow: /ua/n/"
    monkeypatch.setattr(live,"fetch_text",blocked)
    assert live.lookup(CTX)[0]=="robots_denied"
    assert calls==["/robots.txt"]
    monkeypatch.setattr(live,"_LAST",float("-inf"))
    monkeypatch.setattr(live,"_ROBOTS",None)
    def unavailable(path,limit=live.MAX_BYTES):
        if path=="/robots.txt":
            return ROBOTS
        raise OSError("test timeout")
    monkeypatch.setattr(live,"fetch_text",unavailable)
    assert live.lookup(CTX)[0]=="source_network_error" and not live._CACHE


def test_empty_and_oversized_markup():
    with pytest.raises(live.LookupFailure):
        live.parse_cards("<html>access denied</html>",PATH,STAMP)
    with pytest.raises(ValueError):
        live.parse_cards("x"*(live.MAX_BYTES+1),PATH,STAMP)

def test_limited_pilot_daily_cap_and_production_off(monkeypatch):
    authorize(monkeypatch)
    assert live.enabled()
    monkeypatch.setenv("WAREHOUSE_ENV","production")
    assert not live.enabled()
    monkeypatch.setenv("WAREHOUSE_ENV","staging")
    monkeypatch.setattr(live,"_ATTEMPTS",[live.monotonic()]*live.DAILY_LIMIT)
    monkeypatch.setattr(live,"fetch_text",lambda *a:pytest.fail("quota must prevent network"))
    assert live.lookup(CTX)[0]=="daily_limit"
    assert live.lookup_path(dict(CTX,oem="81150 06C41"))==PATH

def test_source_not_found_vs_robots_failure(monkeypatch):
    authorize(monkeypatch)
    def fetch(path,limit=live.MAX_BYTES):
        if path=="/robots.txt":return ROBOTS
        raise live.LookupFailure("source_not_found")
    monkeypatch.setattr(live,"fetch_text",fetch)
    assert live.lookup(CTX)[0]=="source_not_found"
    monkeypatch.setattr(live,"_LAST",float("-inf"))
    monkeypatch.setattr(live,"_ROBOTS",None)
    def unavailable(*args):
        raise live.LookupFailure("source_not_found")
    monkeypatch.setattr(live,"fetch_text",unavailable)
    assert live.lookup(CTX)[0]=="robots_unavailable"


def test_control_markup_with_labels_and_generation():
    # Reconstructed from the real 2026-11-26 Toyota OEM observation, not a
    # live request or claim of current availability.
    rows=live.parse_cards("".join(card(i,p,title="Фара передня ліва у зборі Toyota Camry v70 19-20 галоген + LED",labels="Новий аналог",availability="") for i,p in enumerate([24769,10328,24038],1)),PATH,STAMP)
    groups=live.references(CTX,rows)
    assert len(groups)==1 and groups[0]["condition"]=="new"
    assert groups[0]["availability"]=="unknown" and groups[0]["offer_count"]==3
    assert groups[0]["average"]=="19711.67"
    assert live.condition_for("Відновлений")=="refurbished"
