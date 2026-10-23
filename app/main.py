from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import hashlib, json, re, difflib, os

app = FastAPI(title="CT-200 Document QA API", version="0.1.0")
DATA = Path(__file__).resolve().parent.parent / "data"
STORE = Path(__file__).resolve().parent.parent / "store.json"

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_store():
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {"versions": {}, "latest": None, "selections": {}, "generations": {}}

def save_store(db):
    STORE.write_text(json.dumps(db, indent=2))

def parse_text(text: str):
    """Conservative line-based parser for numbered headings and paragraphs.
    Unsupported/ambiguous lines remain in body text instead of being discarded.
    """
    root = {"id": "root", "heading": "CT-200 Manual", "level": 0, "body_text": "",
            "content_hash": sha(""), "parent_id": None, "children": []}
    stack = [root]
    counter = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', line)
        if match:
            numbering, heading = match.groups()
            level = numbering.count(".") + 1
            # Only classify clearly numbered lines as headings.
            while len(stack) > 1 and stack[-1]["level"] >= level:
                stack.pop()
            parent = stack[-1]
            counter += 1
            node = {"id": f"n{counter}", "heading": heading, "level": level,
                    "body_text": "", "content_hash": "", "parent_id": parent["id"], "children": []}
            parent["children"].append(node)
            stack.append(node)
        else:
            stack[-1]["body_text"] += (("\n" if stack[-1]["body_text"] else "") + line)
    def finish(node):
        node["content_hash"] = sha(node["heading"] + "\n" + node["body_text"])
        for child in node["children"]:
            finish(child)
    finish(root)
    return root

def flatten(node):
    result = [node]
    for child in node.get("children", []):
        result.extend(flatten(child))
    return result

def pdf_to_text(path: Path):
    try:
        import fitz
    except ImportError:
        raise HTTPException(500, "Install requirements.txt; PyMuPDF is required for PDF extraction.")
    doc = fitz.open(path)
    text = "\n".join(page.get_text("text") for page in doc)
    if not text.strip():
        raise HTTPException(422, "PDF has no extractable text. OCR is not implemented; run OCR first.")
    return text

def get_db():
    return load_store()

class IngestRequest(BaseModel):
    version: str = Field(..., description="e.g. v1 or v2")
    text: Optional[str] = None
    filename: Optional[str] = None

class SelectionRequest(BaseModel):
    name: str
    version: str
    node_ids: list[str]

class GenerateRequest(BaseModel):
    selection_id: str
    provider: str = "demo"

@app.get("/")
def home():
    return {"service":"CT-200 Document QA API", "docs":"/docs", "warning":"Demo implementation; validate against supplied CT-200 PDFs before production use."}

@app.post("/ingest")
def ingest(req: IngestRequest):
    db = get_db()
    if req.text:
        text = req.text
    elif req.filename:
        path = (DATA / req.filename).resolve()
        if DATA.resolve() not in path.parents or not path.exists():
            raise HTTPException(404, "PDF filename not found in data/")
        text = pdf_to_text(path)
    else:
        raise HTTPException(400, "Provide text or filename.")
    tree = parse_text(text)
    nodes = flatten(tree)
    prior = db["versions"].get(req.version)
    db["versions"][req.version] = {"tree":tree, "nodes":{n["id"]:n for n in nodes}, "source_hash":sha(text)}
    db["latest"] = req.version
    changes = {"new_version": req.version, "node_count":len(nodes)-1, "previous_version":None, "changed_nodes":[]}
    if prior:
        changes["previous_version"] = req.version
    else:
        previous = [v for v in db["versions"] if v != req.version]
        if previous:
            prev = db["versions"][previous[-1]]
            changes["previous_version"] = previous[-1]
            old_by_path = {}
            def collect(n, path=""):
                p = path + "/" + n["heading"]
                old_by_path[p] = n
                for c in n["children"]: collect(c,p)
            collect(prev["tree"])
            def compare(n, path=""):
                p=path+"/"+n["heading"]
                old=old_by_path.get(p)
                if old:
                    if old["content_hash"] != n["content_hash"]:
                        changes["changed_nodes"].append({"path":p,"status":"content_changed"})
                    else:
                        changes["changed_nodes"].append({"path":p,"status":"unchanged"})
                else:
                    changes["changed_nodes"].append({"path":p,"status":"new_or_moved"})
                for c in n["children"]: compare(c,p)
            compare(tree)
    save_store(db)
    return {"version":req.version,"source_hash":sha(text),"tree":tree,"comparison":changes}

@app.get("/sections")
def sections(version: Optional[str]=None):
    db=get_db(); version=version or db["latest"]
    if not version or version not in db["versions"]: raise HTTPException(404,"Version not found")
    return {"version":version,"sections":db["versions"][version]["tree"]["children"]}

@app.get("/nodes/{node_id}")
def get_node(node_id: str, version: Optional[str]=None):
    db=get_db(); version=version or db["latest"]
    if not version or version not in db["versions"]: raise HTTPException(404,"Version not found")
    node=db["versions"][version]["nodes"].get(node_id)
    if not node: raise HTTPException(404,"Node not found in requested version")
    return {"version":version,"node":node}

@app.get("/search")
def search(q: str, version: Optional[str]=None):
    db=get_db(); version=version or db["latest"]
    if not version or version not in db["versions"]: raise HTTPException(404,"Version not found")
    matches=[]
    for n in db["versions"][version]["nodes"].values():
        if q.lower() in (n["heading"]+" "+n["body_text"]).lower():
            matches.append({"id":n["id"],"heading":n["heading"],"level":n["level"],"content_hash":n["content_hash"]})
    return {"version":version,"query":q,"results":matches}

@app.get("/diff/{node_id}")
def diff_node(node_id: str, from_version: str, to_version: Optional[str]=None):
    db=get_db(); to_version=to_version or db["latest"]
    if from_version not in db["versions"] or to_version not in db["versions"]:
        raise HTTPException(404,"Version not found")
    a=db["versions"][from_version]["nodes"].get(node_id)
    b=db["versions"][to_version]["nodes"].get(node_id)
    if not a or not b:
        return {"changed":True,"summary":"Node ID is missing in one version; IDs are parser-order based and may shift."}
    changed=a["content_hash"] != b["content_hash"]
    return {"changed":changed,"from_version":from_version,"to_version":to_version,
            "summary": "Content hash differs." if changed else "Content hash matches.",
            "before":a["body_text"][:300] if changed else None,
            "after":b["body_text"][:300] if changed else None}

@app.post("/selections")
def create_selection(req: SelectionRequest):
    db=get_db()
    if req.version not in db["versions"]: raise HTTPException(404,"Version not found")
    nodes=db["versions"][req.version]["nodes"]
    missing=[i for i in req.node_ids if i not in nodes]
    if missing: raise HTTPException(404, f"Unknown node IDs: {missing}")
    sid="sel_"+sha(req.name+req.version+"|".join(req.node_ids))[:12]
    db["selections"][sid]={"id":sid,"name":req.name,"version":req.version,
       "nodes":[{"node_id":i,"version":req.version,"heading":nodes[i]["heading"],
                 "body_text":nodes[i]["body_text"],"content_hash":nodes[i]["content_hash"]} for i in req.node_ids]}
    save_store(db)
    return db["selections"][sid]

@app.post("/generate")
def generate(req: GenerateRequest):
    db=get_db()
    selection=db["selections"].get(req.selection_id)
    if not selection: raise HTTPException(404,"Selection not found")
    # Safe deterministic fallback so the API works without an API key.
    cases=[]
    for item in selection["nodes"][:5]:
        context=item["heading"]+": "+item["body_text"]
        cases.append({"title":"Verify requirement: "+item["heading"],
          "preconditions":"Use a test setup appropriate to the selected requirement.",
          "steps":["Set up the device or simulator according to the requirement.","Exercise the behavior described in the selected text.","Record the observed result."],
          "expected_result":"Observed behavior matches the selected source text; derive exact limits from the manual.",
          "source_node_id":item["node_id"],"source_content_hash":item["content_hash"]})
    gid="gen_"+sha(req.selection_id+json.dumps(cases,sort_keys=True))[:12]
    db["generations"][gid]={"id":gid,"selection_id":req.selection_id,"source_version":selection["version"],
       "cases":cases,"mode":"deterministic_demo","staleness":check_staleness(db, selection["nodes"])}
    save_store(db)
    return db["generations"][gid]

def check_staleness(db, selected_nodes):
    latest=db["latest"]
    if not latest: return "unknown"
    current_nodes=db["versions"][latest]["nodes"]
    stale=[]
    for item in selected_nodes:
        node=current_nodes.get(item["node_id"])
        if not node or node["content_hash"] != item["content_hash"]: stale.append(item["node_id"])
    return "stale" if stale else ("current" if all(x["version"]==latest for x in selected_nodes) else "content_matches_latest")

@app.get("/generated")
def retrieve_generated(selection_id: Optional[str]=None, node_id: Optional[str]=None):
    db=get_db(); out=[]
    for gen in db["generations"].values():
        if selection_id and gen["selection_id"] != selection_id: continue
        if node_id and not any(c["source_node_id"]==node_id for c in gen["cases"]): continue
        selection=db["selections"].get(gen["selection_id"],{})
        gen_copy=dict(gen)
        gen_copy["staleness"]=check_staleness(db, selection.get("nodes",[]))
        out.append(gen_copy)
    return {"results":out}
