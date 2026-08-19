from app.pricecharting_client import parse_chart_data, parse_full_prices, parse_search_page
from app.service import match_card_page

SEARCH_HTML = """
<table>
<tr id="product-2368436">
  <td class="image">
    <div>
      <a href="https://www.pricecharting.com/game/pokemon-base-set/booster-box" title="2368436">
        <img class="photo" loading="lazy" src="https://storage.googleapis.com/images.pricecharting.com/abc/60.jpg" />
      </a>
    </div>
  </td>
  <td class="title">
    <a href="https://www.pricecharting.com/game/pokemon-base-set/booster-box" title="2368436">
      Booster Box</a>
  </td>
  <td class="console phone-landscape-hidden">Pokemon Base Set</td>
  <td class="price numeric used_price">$11,696.40</td>
  <td class="price numeric cib_price"></td>
  <td class="price numeric new_price">$12,000.00</td>
</tr>
<tr id="product-999">
  <td class="image"><div><a href="https://www.pricecharting.com/game/pokemon-x/y-pack"><img class="photo" src="https://img/2.jpg" /></a></div></td>
  <td class="title"><a href="https://www.pricecharting.com/game/pokemon-x/y-pack">Booster Pack</a></td>
  <td class="console phone-landscape-hidden">Pokemon XY</td>
  <td class="price numeric used_price">$5.00</td>
  <td class="price numeric cib_price">—</td>
  <td class="price numeric new_price"></td>
</tr>
</table>
"""


def test_parse_search_page_extracts_rows_and_prices():
    rows = parse_search_page(SEARCH_HTML)
    assert len(rows) == 2

    box = rows[0]
    assert box["id"] == "2368436"
    assert box["name"] == "Booster Box"
    assert box["set_name"] == "Pokemon Base Set"
    assert box["url"] == "https://www.pricecharting.com/game/pokemon-base-set/booster-box"
    assert box["used"] == 11696.40
    assert box["cib"] is None
    assert box["new"] == 12000.00
    assert box["image_small"].endswith("60.jpg")

    pack = rows[1]
    assert pack["used"] == 5.00
    assert pack["cib"] is None
    assert pack["new"] is None


def test_parse_chart_data_extracts_series():
    html = (
        "<html><script>if (typeof VGPC == 'undefined') var VGPC = { };\n"
        'VGPC.chart_data = {"boxonly":[[1627797600000,0]],'
        '"used":[[1627797600000,0],[1630476000000,1169640]],"new":[]};'
        "</script></html>"
    )
    data = parse_chart_data(html)
    assert data["used"] == [(1627797600000, 0.0), (1630476000000, 1169640.0)]
    assert data["new"] == []
    assert data["boxonly"] == [(1627797600000, 0.0)]


def test_parse_chart_data_missing_returns_empty():
    assert parse_chart_data("<html>no chart here</html>") == {}


FULL_PRICES_HTML = """
<section id="full-prices">
  <table>
    <tr>
      <td>Ungraded</td>
      <td class="price js-price">$405.00</td>
    </tr>
    <tr>
      <td>Grade 1</td>
      <td class="price js-price">$370.00</td>
    </tr>
    <tr>
      <td>Grade 9</td>
      <td class="price js-price">$2,691.06</td>
    </tr>
    <tr>
      <td>Grade 9.5</td>
      <td class="price js-price">-</td>
    </tr>
    <tr>
      <td>PSA 10</td>
      <td class="price js-price">$28,112.98</td>
    </tr>
    <tr>
      <td>BGS 10 Black</td>
      <td class="price js-price">$182,735.00</td>
    </tr>
  </table>
</section>
<table>
  <tr><td>Grade 7</td><td class="price js-price">$999.99</td></tr>
</table>
"""


def test_parse_full_prices_extracts_psa_ladder():
    prices = parse_full_prices(FULL_PRICES_HTML)
    assert prices == {
        "ungraded": 405.00,
        "1": 370.00,
        "9": 2691.06,
        "10": 28112.98,
    }


def test_parse_full_prices_missing_returns_empty():
    assert parse_full_prices("<html>no guide here</html>") == {}


SEARCH_RESULTS = [
    {"name": "Charizard [1st Edition] #4", "set_name": "Pokemon Base Set", "url": "u1"},
    {"name": "Charizard #4", "set_name": "Pokemon Base Set", "url": "u2"},
    {"name": "Charizard [Shadowless] #4", "set_name": "Pokemon Base Set", "url": "u3"},
    {"name": "Charizard #4", "set_name": "Pokemon Base Set 2", "url": "u4"},
    {"name": "Charizard #4", "set_name": "Pokemon Chinese Base Set", "url": "u5"},
]


def test_match_card_page_prefers_base_printing():
    assert match_card_page(SEARCH_RESULTS, "Charizard", "4", "Base") == "u2"


def test_match_card_page_rejects_wrong_number_and_name():
    assert match_card_page(SEARCH_RESULTS, "Charizard", "5", "Base") is None
    assert match_card_page(SEARCH_RESULTS, "Blastoise", "4", "Base") is None
