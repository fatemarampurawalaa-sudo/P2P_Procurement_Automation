"""AI Procurement Automation: a live Procure-to-Pay (P2P) workflow (demo data only)."""
import json
import random
import time
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pydantic import BaseModel

# ---------- Demo company data (all made-up) ----------
SUPPLIERS = pd.DataFrame({
    "supplier": ["TechZone LLC", "Gulf IT Supplies", "NetLink Solutions", "OfficeHub", "PaperPlus Trading",
                 "Desert Furniture Co", "SmartPrint Services", "CleanCare FM", "EventPro Dubai", "SkillUp Academy"],
    "category": ["IT", "IT", "IT", "Office", "Office", "Furniture", "Printing", "Facilities", "Events", "Training"],
    "rating": [4.6, 4.1, 4.4, 4.3, 3.8, 4.5, 4.0, 3.9, 4.2, 4.5],
    "delivery_days": [5, 8, 7, 3, 6, 12, 4, 2, 10, 7],
})
GENERAL_BIDDERS = [("Al Noor General Trading", 3.9, 9), ("Emirates Supply House", 4.0, 8)]

DEPARTMENTS = {  # budget for the current period, already spent at the start of the demo
    "IT": {"manager": "Omar (IT Manager)", "requester": "Omar", "budget": 120000, "spent": 70000},
    "HR": {"manager": "Sara (HR Manager)", "requester": "Sara", "budget": 25000, "spent": 9000},
    "Finance": {"manager": "Ali (Finance Manager)", "requester": "Ali", "budget": 25000, "spent": 8000},
    "Operations": {"manager": "Rashid (Ops Manager)", "requester": "Rashid", "budget": 70000, "spent": 30000},
    "Marketing": {"manager": "Lina (Marketing Manager)", "requester": "Lina", "budget": 90000, "spent": 62000},
    "Admin": {"manager": "Noor (Admin Manager)", "requester": "Noor", "budget": 20000, "spent": 16500},
}
FINANCE_DIRECTOR = "Khalid (Finance Director)"
AUTO_LIMIT, MANAGER_LIMIT, QUOTES_LIMIT = 5000, 25000, 25000

# item, category, department, unit price range (AED), quantity range
CATALOG = [
    ("Laptops", "IT", "IT", (3800, 4500), (2, 10)), ("Monitors", "IT", "IT", (650, 900), (2, 8)),
    ("Software licences", "IT", "IT", (300, 600), (5, 20)), ("Network switch", "IT", "IT", (2500, 4000), (1, 2)),
    ("Server", "IT", "IT", (28000, 36000), (1, 1)),
    ("Handbook printing", "Printing", "HR", (3, 4), (200, 600)), ("Team event catering", "Events", "HR", (40, 70), (20, 60)),
    ("Leadership training", "Training", "HR", (1500, 3000), (1, 3)),
    ("A4 paper boxes", "Office", "Finance", (90, 100), (10, 40)), ("Printer toner", "Office", "Finance", (250, 350), (4, 12)),
    ("Audit software", "IT", "Finance", (8000, 12000), (1, 1)),
    ("Warehouse deep cleaning", "Facilities", "Operations", (6000, 11000), (1, 1)),
    ("Safety equipment", "Facilities", "Operations", (120, 200), (10, 40)),
    ("Forklift maintenance", "Facilities", "Operations", (3000, 5000), (1, 1)),
    ("75-inch display screens", "IT", "Marketing", (11000, 13000), (1, 3)),
    ("Expo booth", "Events", "Marketing", (15000, 30000), (1, 1)), ("Brochure printing", "Printing", "Marketing", (2, 3), (1000, 5000)),
    ("Ergonomic chairs", "Furniture", "Admin", (900, 1300), (2, 8)), ("Office supplies", "Office", "Admin", (15, 40), (20, 80)),
    ("Coffee machine", "Office", "Admin", (2500, 4000), (1, 1)),
]
STAGES = ["Request", "Approval", "Quotes", "PO", "Received", "Invoice", "Paid"]
STAGE_ICONS = {"Request": "📥", "Approval": "✅", "Quotes": "📄", "PO": "🧾", "Received": "📦", "Invoice": "🔍", "Paid": "💸"}
DONE = {"Paid", "Rejected", "On hold"}


# ---------- Workflow engine ----------
def log(state, icon, text):
    state["log"].append({"time": state["clock"].strftime("%a %H:%M"), "icon": icon, "text": text})
    state["log"] = state["log"][-200:]


def remaining(state, dept):
    return state["budget"][dept]["budget"] - state["budget"][dept]["spent"]


def new_request(state):
    item, category, dept, (p_lo, p_hi), (q_lo, q_hi) = random.choice(CATALOG)
    qty = random.randint(q_lo, q_hi)
    unit = round(random.uniform(p_lo, p_hi), 2 if p_hi < 10 else 0)
    state["next_id"] += 1
    req = {"pr_id": f"PR-{state['next_id']}", "item": item, "category": category, "dept": dept,
           "requester": DEPARTMENTS[dept]["requester"], "qty": qty, "unit": unit, "amount": round(qty * unit),
           "urgent": random.random() < 0.25, "stage": "Request", "wait": 0, "note": "", "flag": False,
           "supplier": None}
    state["items"].append(req)
    state["stats"]["requests"] += 1
    urgent = " · URGENT" if req["urgent"] else ""
    log(state, "📥", f"{req['pr_id']} new request from {req['requester']} ({dept}): {qty} × {item} "
                     f"= AED {req['amount']:,}{urgent}")


def route(state, r):
    """Approval rules: budget check first, then amount limits."""
    if r["amount"] > remaining(state, r["dept"]):
        r["approver"], r["exception"] = FINANCE_DIRECTOR, True
        state["stats"]["budget_exceptions"] += 1
        log(state, "🚩", f"{r['pr_id']} over {r['dept']} budget (AED {max(0, remaining(state, r['dept'])):,.0f} left) "
                         f"→ budget exception to {FINANCE_DIRECTOR}")
    elif r["amount"] < AUTO_LIMIT:
        state["stats"]["auto_approved"] += 1
        r["stage"], r["note"] = "PO", "auto-approved"
        log(state, "✅", f"{r['pr_id']} auto-approved (under AED {AUTO_LIMIT:,}), no human needed")
        return
    else:
        r["approver"] = DEPARTMENTS[r["dept"]]["manager"] if r["amount"] <= MANAGER_LIMIT else FINANCE_DIRECTOR
        r["exception"] = False
        log(state, "🔀", f"{r['pr_id']} AED {r['amount']:,} → sent to {r['approver']} for approval")
    r["stage"], r["wait"], r["note"] = "Approval", 0, "waiting " + r["approver"].split(" (")[0]
    r["needs"] = random.randint(1, 5)
    r["remind_at"] = 2 if r["urgent"] else 3


def approve(state, r):
    r["wait"] += 1
    if r["wait"] == r["remind_at"] and r["wait"] < r["needs"]:
        state["stats"]["reminders"] += 1
        r["note"] += " · ⏰ reminded"
        log(state, "⏰", f"Reminder sent to {r['approver']} for {r['pr_id']} "
                         f"({'urgent, ' if r['urgent'] else ''}no reply yet)")
    if r["wait"] < r["needs"]:
        return
    who = r["approver"].split(" (")[0]
    roll = random.random()
    if r["exception"]:
        decision = "Approved" if roll < 0.35 else "Rejected" if roll < 0.7 else "On hold"
    else:
        decision = "Approved" if roll < 0.9 else "Rejected"
    if decision == "Approved":
        r["stage"] = "Quotes" if r["amount"] > QUOTES_LIMIT else "PO"
        r["note"] = f"approved by {who}"
        log(state, "👍", f"{r['pr_id']} approved by {who}")
    else:
        r["stage"], r["note"] = decision, f"{decision.lower()} by {who}"
        state["stats"]["rejected" if decision == "Rejected" else "on_hold"] += 1
        log(state, "❌" if decision == "Rejected" else "⏸️", f"{r['pr_id']} {decision.lower()} by {who}")


def compare_quotes(state, r):
    bidders = SUPPLIERS[SUPPLIERS["category"] == r["category"]][["supplier", "rating", "delivery_days"]]
    if len(bidders) < 3:
        extra = pd.DataFrame(GENERAL_BIDDERS, columns=["supplier", "rating", "delivery_days"])
        bidders = pd.concat([bidders, extra]).head(3)
    quotes = bidders.copy()
    quotes["price"] = [round(r["amount"] * random.uniform(0.9, 1.08)) for _ in range(len(quotes))]
    quotes["days"] = [max(1, d + random.randint(-2, 6)) for d in quotes["delivery_days"]]
    quotes["score"] = (0.5 * quotes["price"].min() / quotes["price"] + 0.3 * quotes["days"].min() / quotes["days"]
                       + 0.2 * quotes["rating"] / 5) * 100
    best = quotes.sort_values("score", ascending=False).iloc[0]
    cheapest = quotes.sort_values("price").iloc[0]
    r["supplier"], r["amount"], r["days"] = best["supplier"], int(best["price"]), int(best["days"])
    r["note"] = f"{best['supplier']} won"
    extra_note = "" if best["supplier"] == cheapest["supplier"] else f" (beat cheaper {cheapest['supplier']} on speed/quality)"
    log(state, "📄", f"{r['pr_id']} {len(quotes)} quotes compared → {best['supplier']} wins, "
                     f"score {best['score']:.0f}/100{extra_note}")
    r["stage"] = "PO"


def create_po(state, r):
    if r["supplier"] is None:
        best = SUPPLIERS[SUPPLIERS["category"] == r["category"]].sort_values("rating", ascending=False).iloc[0]
        r["supplier"], r["days"] = best["supplier"], int(best["delivery_days"])
    state["next_po"] += 1
    r["po_no"] = f"PO-{state['next_po']}"
    state["budget"][r["dept"]]["spent"] += r["amount"]
    state["stats"]["pos"] += 1
    state["stats"]["po_value"] += r["amount"]
    r["stage"], r["wait"], r["deliver_in"] = "Received", 0, max(1, round(r["days"] / 2))
    r["note"] = f"{r['po_no']} · {r['supplier']}"
    log(state, "🧾", f"{r['po_no']} created and sent to {r['supplier']} for {r['pr_id']} · AED {r['amount']:,}")


def receive(state, r):
    r["wait"] += 1
    if r["wait"] < r["deliver_in"]:
        return
    short = r["qty"] > 3 and random.random() < 0.12
    r["received"] = r["qty"] - (random.randint(1, min(3, r["qty"] - 1)) if short else 0)
    r["stage"], r["note"] = "Invoice", f"received {r['received']}/{r['qty']}"
    if short:
        log(state, "⚠️", f"{r['po_no']} goods received: only {r['received']} of {r['qty']} × {r['item']}")
    else:
        log(state, "📦", f"{r['po_no']} goods received in full ({r['qty']} × {r['item']})")


def check_invoice(state, r):
    if r["flag"]:  # waiting for the supplier to fix a wrong invoice
        r["wait"] += 1
        if r["wait"] >= 3:
            r["stage"], r["note"], r["flag"] = "Paid", "paid after credit note", False
            state["stats"]["paid"] += 1
            log(state, "📨", f"{r['supplier']} sent a credit note for {r['po_no']} → paid the correct amount")
        return
    billed_price = r["amount"]
    if random.random() < 0.08:
        billed_price = round(r["amount"] * random.uniform(1.05, 1.15))
    if r["received"] < r["qty"]:
        saved = round((r["qty"] - r["received"]) * r["unit"])
        problem = f"billed {r['qty']}, received {r['received']}"
    elif billed_price != r["amount"]:
        saved = billed_price - r["amount"]
        problem = f"billed AED {billed_price:,}, PO says AED {r['amount']:,}"
    else:
        r["stage"], r["note"] = "Paid", "3-way match ✓"
        state["stats"]["paid"] += 1
        log(state, "💸", f"{r['po_no']} 3-way match OK (PO = received = invoice) → paid AED {r['amount']:,}")
        return
    r["flag"], r["wait"], r["note"] = True, 0, "🚩 " + problem
    state["stats"]["flagged"] += 1
    state["stats"]["saved"] += saved
    log(state, "🚩", f"{r['po_no']} invoice from {r['supplier']} blocked: {problem} · AED {saved:,} overpayment stopped")


def step(state):
    """One tick of the workflow = 2 simulated hours."""
    state["clock"] += pd.Timedelta(hours=2)
    state["tick"] += 1
    if state["tick"] % 30 == 0:
        for b in state["budget"].values():
            b["spent"] = round(b["budget"] * random.uniform(0.1, 0.35))
        log(state, "📅", "New budget period: department budgets refreshed")

    for r in [r for r in state["items"] if r["stage"] not in DONE]:
        stage = r["stage"]
        if stage == "Request":
            route(state, r)
        elif stage == "Approval":
            approve(state, r)
        elif stage == "Quotes":
            compare_quotes(state, r)
        elif stage == "PO":
            create_po(state, r)
        elif stage == "Received":
            receive(state, r)
        elif stage == "Invoice":
            check_invoice(state, r)

    for _ in range(random.choices([0, 1, 2], weights=[0.25, 0.5, 0.25])[0]):
        new_request(state)

    active = [r for r in state["items"] if r["stage"] not in DONE]
    finished = [r for r in state["items"] if r["stage"] in DONE][-40:]
    state["items"] = finished + active


def reset(state):
    random.seed()
    state.update({
        "clock": pd.Timestamp("2026-11-17 08:00"), "tick": 0, "next_id": 100, "next_po": 5000,
        "items": [], "log": [],
        "budget": {d: {"budget": v["budget"], "spent": v["spent"]} for d, v in DEPARTMENTS.items()},
        "stats": dict.fromkeys(["requests", "auto_approved", "budget_exceptions", "reminders", "rejected",
                                "on_hold", "pos", "po_value", "flagged", "saved", "paid"], 0),
    })
    for _ in range(20):  # warm up so the board is not empty
        step(state)


# ---------- AI document reader (Gemini) ----------
class PurchaseRequest(BaseModel):
    requester: str
    department: Literal["IT", "HR", "Finance", "Operations", "Marketing", "Admin"]
    item: str
    quantity: int
    estimated_total_aed: float
    urgency: Literal["Low", "Normal", "High"]


class Quote(BaseModel):
    supplier: str
    total_aed: float
    delivery_days: int
    warranty_years: int


class Invoice(BaseModel):
    invoice_no: str
    po_no: str
    quantity: int
    total_aed: float


SAMPLE_EMAILS = """EMAIL 1 - From: Omar (IT)
Hi team, we have 10 new joiners starting next month and need laptops for them.
Something like Dell Latitude, roughly AED 4,200 each. Please arrange within 2 weeks.

EMAIL 2 - From: Sara (HR)
Hello, can we print 500 copies of the new employee handbook? I was told it's about AED 3 per copy. No rush.

EMAIL 3 - From: Noor (Admin)
Our reception chairs are broken. We need 6 ergonomic chairs, around 1,100 dirhams each.

EMAIL 4 - From: Rashid (Operations)
URGENT - the warehouse needs a deep cleaning service before the audit next week. CleanCare quoted AED 9,500."""

SAMPLE_QUOTES = """QUOTE 1 - TechZone LLC: 10 x Dell Latitude 5450 at AED 4,050 per unit (total AED 40,500).
Delivery within 5 days. Includes 3-year warranty.

QUOTE 2 - Gulf IT Supplies: Best price for you, AED 3,850 each, so 38,500 for 10 laptops.
Stock arrives in 3 weeks. Warranty 1 year.

QUOTE 3 - NetLink Solutions: 10 laptops for AED 39,900 total. Delivery one week. 3 years warranty."""

SAMPLE_INVOICES = """INVOICE INV-T-889 from TechZone LLC - Ref PO-5001: 10 x Dell Latitude 5450 = AED 40,500

Invoice SP-2231 | SmartPrint Services | Your PO: PO-5002 | 500 handbook copies at 3.50 each. Total due: AED 1,750

OfficeHub invoice OH-4410 for order PO-5004: 40 boxes A4 paper x AED 95 = AED 3,800"""


@st.cache_data(show_spinner=False)
def ai_extract(kind, text):
    from google import genai
    from google.genai import types
    schema = {"emails": list[PurchaseRequest], "quotes": list[Quote], "invoices": list[Invoice]}[kind]
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(api_version="v1beta"))  # "-latest" model names live on v1beta
    prompt = ("You are a procurement assistant. Extract one row per document below. "
              "Calculate totals as quantity x unit price and convert weeks to days (1 week = 7 days).\n\n" + text)
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-flash-lite-latest", contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema))
            return pd.DataFrame(json.loads(response.text))
        except Exception as error:
            last_error = error
            time.sleep(4)
    raise RuntimeError(str(last_error))  # errors are not cached, so the next click tries again


# ---------- Page ----------
st.set_page_config(page_title="AI Procurement Automation", page_icon="🛒", layout="wide")
st.title("🛒 AI Procurement Automation")
st.caption("A live Procure-to-Pay (P2P) workflow: purchase requests are routed, approved, quoted, ordered, "
           "received and invoice-checked automatically. People only step in when a decision is needed.")
st.warning("Demo project: all departments, suppliers, requests and invoices are made-up data.", icon="⚠️")

if "items" not in st.session_state:
    reset(st.session_state)

SPEEDS = {"Slow": 2.5, "Normal": 1.5, "Fast": 0.7}  # seconds between workflow steps


def card(title, value, color):
    return (f"<div style='background:#111a33;border-radius:12px;padding:10px 14px'>"
            f"<div style='color:#8c9bb9;font-size:0.8rem'>{title}</div>"
            f"<div style='color:{color};font-size:1.5rem;font-weight:700'>{value}</div></div>")


def item_card(r):
    if r["flag"] or r["stage"] in ("Rejected", "On hold"):
        border = "#eb4034"
    elif r["urgent"] and r["stage"] not in DONE:
        border = "#f5b041"
    elif r["note"] == "auto-approved" or r["stage"] == "Paid":
        border = "#2ecc71"
    else:
        border = "#4a7bd0"
    return (f"<div style='border-left:5px solid {border};background:#111a33;color:#e1e8f5;padding:6px 9px;"
            f"border-radius:7px;margin-bottom:6px;font-size:0.78rem;line-height:1.3'>"
            f"<b>{r['pr_id']}</b> · AED {r['amount']:,}<br>{r['item']}<br>"
            f"<span style='color:#8c9bb9'>{r['note']}</span></div>")


def live_view():
    state = st.session_state
    if state.get("live_on"):
        step(state)
    s = state["stats"]

    st.markdown(f"#### 🕘 {state['clock']:%A %d %b · %H:%M}")
    cards = [("Requests received", f"{s['requests']:,}", "#e1e8f5"),
             ("Auto-approved", f"{s['auto_approved']:,}", "#2ecc71"),
             ("⏰ Reminders sent", f"{s['reminders']:,}", "#f5b041"),
             ("🚩 Budget exceptions", f"{s['budget_exceptions']:,}", "#eb4034"),
             (f"POs · AED {s['po_value'] / 1e6:,.1f}M", f"{s['pos']:,}", "#e1e8f5"),
             ("🚩 Invoices blocked", f"{s['flagged']:,}", "#eb4034"),
             ("💰 Money saved", f"AED {s['saved']:,.0f}", "#2ecc71")]
    for col, (title, value, color) in zip(st.columns(7), cards):
        col.markdown(card(title, value, color), unsafe_allow_html=True)

    st.markdown("##### 🔀 Pipeline")
    for col, stage in zip(st.columns(7), STAGES):
        in_stage = [r for r in state["items"] if r["stage"] == stage]
        col.markdown(f"<div style='font-weight:700;margin-bottom:4px'>{STAGE_ICONS[stage]} {stage} "
                     f"<span style='color:#8c9bb9'>({len(in_stage)})</span></div>", unsafe_allow_html=True)
        col.markdown("".join(item_card(r) for r in in_stage[::-1][:4]) or
                     "<div style='color:#8c9bb9;font-size:0.8rem'>—</div>", unsafe_allow_html=True)

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown("##### 🤖 Activity log")
        rows = "".join(f"<div style='padding:3px 0;border-bottom:1px solid #1c2a4a;font-size:0.82rem'>"
                       f"<span style='color:#8c9bb9'>{e['time']}</span> &nbsp;{e['icon']} {e['text']}</div>"
                       for e in state["log"][::-1][:14])
        st.markdown(f"<div style='background:#0b1224;color:#e1e8f5;border-radius:10px;padding:8px 12px'>{rows}</div>",
                    unsafe_allow_html=True)
    with right:
        st.markdown("##### 💼 Department budgets (current period)")
        b = pd.DataFrame(state["budget"]).T
        b["used"] = (b["spent"] / b["budget"]).clip(upper=1.2)
        colors = ["#eb4034" if u > 0.9 else "#f5b041" if u > 0.75 else "#2ecc71" for u in b["used"]]
        fig = go.Figure(go.Bar(x=b["used"] * 100, y=b.index, orientation="h", marker_color=colors,
                               text=[f"{u:.0%} · AED {sp:,.0f} / {bu:,.0f}" for u, sp, bu in
                                     zip(b["used"], b["spent"], b["budget"])],
                               textposition="inside", insidetextanchor="start"))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0b1224",
                          plot_bgcolor="#0b1224", font=dict(color="#e1e8f5"),
                          xaxis=dict(range=[0, 120], ticksuffix="%", gridcolor="#1c2a4a"))
        st.plotly_chart(fig, key="budget_chart", config={"displayModeBar": False})


tab_live, tab_ai, tab_rules = st.tabs(["⚙️ Live Workflow", "🤖 AI Document Reader", "📋 Workflow Rules"])

with tab_live:
    c1, c2, c3 = st.columns([1.2, 1.5, 1])
    c1.toggle("▶️ Run workflow", key="live_on")
    c2.select_slider("Speed", options=list(SPEEDS), value="Normal", key="live_speed")
    if c3.button("🔄 Reset"):
        reset(st.session_state)
    run_every = SPEEDS[st.session_state.get("live_speed", "Normal")] if st.session_state.get("live_on") else None
    st.fragment(run_every=run_every)(live_view)()

with tab_ai:
    st.markdown("The workflow starts from **messy documents**. Here Gemini reads them and turns them into clean "
                "data, with no manual typing. Pick a document type and click **Read with AI**.")
    kind = st.radio("Document type", ["📧 Purchase request emails", "📄 Supplier quotes", "🧾 Supplier invoices"],
                    horizontal=True)
    key, text = {"📧 Purchase request emails": ("emails", SAMPLE_EMAILS),
                 "📄 Supplier quotes": ("quotes", SAMPLE_QUOTES),
                 "🧾 Supplier invoices": ("invoices", SAMPLE_INVOICES)}[kind]
    doc_col, result_col = st.columns(2)
    doc_col.markdown("**Original documents**")
    doc_col.code(text, language=None, wrap_lines=True)
    result_col.markdown("**What the AI extracted**")
    if result_col.button("🤖 Read with AI", type="primary"):
        try:
            with st.spinner("Gemini is reading the documents..."):
                result = ai_extract(key, text)
        except Exception as error:
            result = None
            result_col.error("The AI service could not read the documents. Please try again in a minute.")
            result_col.caption(f"Details: {str(error)[:300]}")
        if result is not None:
            result_col.dataframe(result, hide_index=True)
            result_col.success(f"{len(result)} documents turned into structured data.")

with tab_rules:
    st.markdown(f"""
| Step | Rule |
|---|---|
| 🚩 **Budget check** | Request bigger than the department's remaining budget → **budget exception** to the Finance Director |
| ✅ **Auto-approval** | Under **AED {AUTO_LIMIT:,}** → approved automatically, no human needed |
| 👤 **Manager approval** | AED {AUTO_LIMIT:,} – {MANAGER_LIMIT:,} → department manager |
| 🏦 **Finance Director** | Over **AED {MANAGER_LIMIT:,}** → Finance Director |
| ⏰ **Reminders** | No reply → reminder after 4 hours (urgent) or 6 hours (normal) |
| 📄 **Quotes** | Over **AED {QUOTES_LIMIT:,}** → 3 quotes compared on price (50%), delivery (30%) and supplier rating (20%) |
| 🧾 **Purchase order** | Created automatically for every approved request and sent to the chosen supplier |
| 🔍 **3-way match** | Invoice is paid only if **PO = goods received = invoice**; otherwise payment is blocked until the supplier sends a credit note |
""")
