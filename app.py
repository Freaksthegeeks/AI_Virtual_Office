import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import datetime
from langfuse_connection import flush_langfuse, get_langfuse_client, initialize_langfuse

load_dotenv()

app = FastAPI(title="Project Manager Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


class GenerateRequest(BaseModel):
    project_idea: str


@app.get("/", response_class=HTMLResponse)
def read_index() -> HTMLResponse:
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.on_event("startup")
def init_langfuse():
    initialize_langfuse()


@app.on_event("shutdown")
def shutdown_langfuse():
    flush_langfuse()


@app.get("/langfuse/usage")
def langfuse_usage(limit: int = 50, since_hours: int = 24):
    try:
        client = get_langfuse_client()
        to_ts = datetime.datetime.utcnow()
        from_ts = to_ts - datetime.timedelta(hours=since_hours)
        traces = client.api.trace.list(limit=limit, from_timestamp=from_ts, to_timestamp=to_ts, fields="core,metrics")
        data = traces.model_dump()
        total_cost = 0.0
        for t in data.get("data", []):
            # Use totalCost from trace if available
            cost = t.get("totalCost") or t.get("total_cost") or 0.0
            try:
                total_cost += float(cost)
            except:
                pass
        return {"total_traces": len(data.get("data", [])), "total_cost_usd": round(total_cost, 9), "traces": data.get("data", [])}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/local-usage")
def local_usage():
    path = os.path.join(os.getcwd(), "langfuse_usage.jsonl")
    if not os.path.exists(path):
        return {"total_records": 0, "total_cost_usd": 0.0, "records": []}

    total_cost = 0.0
    records = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except:
                    continue
                records.append(obj)
                usage = obj.get("usage", {}) or {}
                est = usage.get("estimated_cost_usd") or usage.get("estimated_cost") or 0.0
                try:
                    total_cost += float(est)
                except:
                    pass
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return {"total_records": len(records), "total_cost_usd": round(total_cost, 9), "records": records}


@app.post("/generate")
def generate(request: GenerateRequest):
    try:
        from main import project_manager_agent

        result = project_manager_agent(request.project_idea)
        try:
            # flush Langfuse events so they appear immediately in the dashboard
            flush_langfuse()
        except Exception:
            pass
        return {"result": result}
    except Exception as exc:
        error_msg = str(exc)
        print(f"Backend error: {error_msg}", flush=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": error_msg,
                "hint": "Check API keys in .env file and ensure Groq API key is valid."
                if "Groq" in error_msg
                else None,
            },
        )
