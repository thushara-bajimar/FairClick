"""Render the project's Mermaid diagrams to PNG (docs/diagrams/) for the PDF report.

Uses Playwright + Mermaid loaded from the jsDelivr CDN (network access required).
    python scripts/render_diagrams.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagrams"

DIAGRAMS = {
    "system_architecture": """
flowchart LR
    U[User] --> D[React dashboard<br/>Vite + Tailwind]
    D -->|REST /api| API[FastAPI backend]
    API --> DB[(fairclick.db<br/>SQLite)]
    API -->|start session| ORCH[Orchestrator<br/>one thread per session]
    ORCH --> AG[Five agents]
    AG --> NAV[Playwright Chromium]
    NAV -->|allowlist: /sites/* only| SIMS[Five simulated websites]
    SIMS --> SIMDB[(sim_sites.db)]
    ORCH --> EVF[Evidence screenshots]
    D -->|approve / reject| API
""",
    "multi_agent": """
flowchart TB
    ORCH{{Orchestrator}}
    NAV[Browser Navigation Agent<br/>observe DOM, reveal, execute]
    DET[Dark Pattern Detection Agent<br/>10-category taxonomy]
    REA[Consumer Rights Reasoning Agent<br/>goal scoring, form preparation]
    EVI[Evidence Collection Agent<br/>screenshots, URLs, text, log]
    SAF[Safety and Approval Agent<br/>risk classes, injection screening]
    HUM([Human approval])
    ORCH -->|observe / execute| NAV
    NAV -->|Observation| ORCH
    ORCH -->|Observation| DET
    DET -->|Detections| EVI
    ORCH -->|Observation + memory| REA
    REA -->|ProposedAction| SAF
    SAF -->|irreversible| HUM
    HUM -->|approve / reject| ORCH
    SAF -->|verdict| ORCH
""",
    "agent_loop": """
sequenceDiagram
    participant O as Orchestrator
    participant N as Navigator
    participant S as Safety
    participant D as Detector
    participant E as Evidence
    participant R as Reasoner
    participant H as Human
    loop every step
        O->>N: observe()
        N-->>O: Observation
        O->>S: screen_content()
        O->>D: analyze()
        D-->>E: detections
        E-->>E: screenshot + record
        O->>R: decide()
        R-->>O: ProposedAction
        O->>S: review(action)
        alt irreversible
            O->>H: approval request
            H-->>O: approve / reject
        end
        O->>N: execute(action)
    end
""",
    "database_er": """
erDiagram
    users ||--o{ tasks : creates
    users ||--o{ user_settings : has
    tasks ||--o{ agent_sessions : runs
    agent_sessions ||--o{ agent_actions : logs
    agent_sessions ||--o{ detections : finds
    detections ||--o| evidence_records : documents
    agent_sessions ||--o{ approval_requests : raises
    approval_requests ||--o| approval_decisions : decided
    agent_sessions ||--o| task_results : produces
    agent_sessions ||--o{ security_incidents : records
""",
    "approval_flow": """
flowchart LR
    A[Reasoner proposes action] --> B{Safety review}
    B -->|purchase / offer / off-domain / credential| X[BLOCKED<br/>never executed]
    B -->|navigation, reveal| C[SAFE: execute]
    B -->|fill, tick, select| R[REVERSIBLE: execute]
    B -->|POST submit / confirm| P[IRREVERSIBLE]
    P --> Q[Approval request:<br/>what, why, data, consequences]
    Q -->|approve| V{Form unchanged?}
    V -->|yes| EX[Execute submission]
    V -->|no| ST[Abort]
    Q -->|reject / expire / stop| ST
""",
}

HTML = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>body{margin:0;background:#fff;font-family:Arial} #c{display:inline-block;padding:16px}</style></head>
<body><div id="c"><pre class="mermaid">%s</pre></div>
<script>mermaid.initialize({startOnLoad:true, theme:'neutral', flowchart:{htmlLabels:true}});</script></body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
        for name, src in DIAGRAMS.items():
            page.set_content(HTML % src.strip(), wait_until="networkidle")
            page.wait_for_selector("#c svg", timeout=20000)
            page.locator("#c").screenshot(path=str(OUT / f"{name}.png"))
            print("rendered", name)
        browser.close()


if __name__ == "__main__":
    main()
