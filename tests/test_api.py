from fastapi.testclient import TestClient
from app.main import app, STORE
import os
client=TestClient(app)

def setup_function():
    if STORE.exists(): STORE.unlink()

def test_ingest_sections_and_search():
    r=client.post("/ingest",json={"version":"v1","text":"1 Safety\n2 Cuff\nUse proper cuff.\n3 Operation\nPress start."})
    assert r.status_code==200
    assert client.get("/sections?version=v1").status_code==200
    assert len(client.get("/search?q=cuff&version=v1").json()["results"]) >= 1

def test_duplicate_headings_remain_distinct():
    r=client.post("/ingest",json={"version":"v1","text":"1 Safety\n1 Safety\nRepeated heading."})
    assert r.status_code==200
    children=r.json()["tree"]["children"]
    assert len(children)==2
    assert children[0]["id"] != children[1]["id"]

def test_selection_pins_source_and_generation_retrieval():
    client.post("/ingest",json={"version":"v1","text":"1 Safety\nUse cuff safely."})
    node=client.get("/sections?version=v1").json()["sections"][0]
    s=client.post("/selections",json={"name":"Safety review","version":"v1","node_ids":[node["id"]]})
    assert s.status_code==200
    g=client.post("/generate",json={"selection_id":s.json()["id"]})
    assert g.status_code==200 and len(g.json()["cases"]) >= 1
    assert client.get("/generated?selection_id="+s.json()["id"]).status_code==200

def test_changed_content_is_flagged():
    client.post("/ingest",json={"version":"v1","text":"1 Safety\nUse cuff safely."})
    client.post("/ingest",json={"version":"v2","text":"1 Safety\nUse cuff safely every time."})
    node=client.get("/sections?version=v1").json()["sections"][0]
    selection=client.post("/selections",json={"name":"Old","version":"v1","node_ids":[node["id"]]}).json()
    gen=client.post("/generate",json={"selection_id":selection["id"]})
    assert gen.status_code==200
    assert client.get("/generated?selection_id="+selection["id"]).json()["results"][0]["staleness"]=="stale"
