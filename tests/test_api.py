import json

from fastapi.testclient import TestClient


def test_startup_health_and_analytics(client):
    assert client.get("/").status_code == 200
    health = client.get("/api/health").json()
    assert health["active_demo_case"] == "b2b_agency"
    assert health["competitor_count"] == 5
    assert health["snapshot_count"] == 10
    rows = client.get("/api/competitors").json()
    funnel = next(row for row in rows if row["name"] == "AutoFunnel Pro")
    assert funnel["min_price"] == 24900
    assert funnel["unread_alert_count"] == 1
    assert funnel["battlecard"]
    summary = client.get("/api/analytics/overview").json()
    assert summary["own_cro_score"] == 86
    assert summary["market_median_min_price"] == 33450
    assert summary["price_index"] == 104.63
    assert summary["price_currency"] == "RUB"
    assert len(summary["radar_axes"]) == len(summary["radar"]) == len(summary["price_matrix"]) == 5


def test_create_and_capture_upload_diff_and_ack(client):
    response = client.post("/api/competitors", json={
        "name": "Test Company", "domain": "test.example", "segment": "direct",
    })
    assert response.status_code == 201
    brand = response.json()["id"]
    response = client.post("/api/pages", json={
        "competitor_id": brand, "page_type": "pricing", "url": "https://test.example/pricing",
    })
    assert response.status_code == 201
    page = response.json()["id"]

    note = {"competitor_strength": "A", "our_counter_offer": "B", "sales_objection_script": "C"}
    first = client.put(f"/api/competitors/{brand}/battlecard", json=note).json()
    updated = client.put(f"/api/competitors/{brand}/battlecard", json=note | {"our_counter_offer": "D"}).json()
    assert first["id"] == updated["id"]
    assert updated["our_counter_offer"] == "D"

    response = client.post("/api/snapshots/capture", json={
        "page_id": page, "mode": "raw_html", "content": "<h1>Тариф</h1><p>800 ₽</p>",
    })
    assert response.status_code == 201
    old = response.json()["snapshot"]
    assert response.json()["alerts"] == []
    response = client.post("/api/snapshots/upload", data={"page_id": page}, files={
        "file": ("price.html", "<h1>Тариф</h1><p>500 ₽</p>".encode(), "text/html"),
    })
    assert response.status_code == 201
    result = response.json()
    new = result["snapshot"]
    alert, = result["alerts"]
    assert alert["change_type"] == "price_drop"
    matched = client.get("/api/snapshots/diff", params={"old_id": old["id"], "new_id": new["id"]}).json()
    assert matched["changes"][0]["diff_details"]["delta"] == -300
    response = client.post("/api/snapshots/upload", data={"page_id": page}, files={
        "file": ("new.JSON", json.dumps({"h1_text": "Тариф", "prices": [900]}), "application/json"),
    })
    assert response.status_code == 201
    assert response.json()["alerts"][0]["change_type"] == "price_hike"
    detail = client.get(f"/api/competitors/{brand}").json()
    assert [s["min_price"] for s in detail["pages"][0]["snapshots"]] == [900, 500, 800]
    acknowledged = client.patch(f"/api/alerts/{alert['id']}/ack").json()
    assert acknowledged["is_acknowledged"] is True
    filtered = client.get("/api/alerts", params={"severity": "high", "is_acknowledged": True}).json()
    assert [item["id"] for item in filtered] == [alert["id"]]


def test_preview_does_not_persist(client):
    response = client.post("/api/snapshots/preview", json={
        "mode": "json_snapshot", "content": {"prices": [150, 299], "currency": "USD"},
    })
    assert response.status_code == 200
    assert response.json()["min_price"] == 150
    assert client.get("/api/health").json()["snapshot_count"] == 10
    assert client.post("/api/snapshots/preview", json={"mode": "live_url"}).status_code == 422
    assert client.post("/api/snapshots/preview", json={"mode": "json_snapshot", "content": "bad"}).status_code == 422


def test_demo_reset_is_repeatable_and_survives_restart(client):
    cases = client.get("/api/demo/cases").json()
    assert {case["case_id"] for case in cases} == {"b2b_agency", "edtech"}
    assert client.post("/api/demo/reset", json={"case_id": "bad"}).status_code == 422
    for _ in range(2):
        reset = client.post("/api/demo/reset", json={"case_id": "edtech"})
        assert reset.status_code == 200
        assert reset.json()["snapshot_count"] == 10
        assert reset.json()["competitor_count"] == 5

    overview = client.get("/api/analytics/overview").json()
    assert overview["own_cro_score"] == 88
    assert overview["own_min_price"] == 29900
    alerts = client.get("/api/alerts").json()
    assert {item["change_type"] for item in alerts} >= {"price_hike", "price_drop", "h1_change", "offer_pivot"}
    with TestClient(client.app) as restarted:
        health = restarted.get("/api/health").json()
        assert health["active_demo_case"] == "edtech"
        assert health["snapshot_count"] == 10
