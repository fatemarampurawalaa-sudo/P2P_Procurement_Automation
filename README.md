# 🛒 AI Procurement Automation: Live Procure-to-Pay Workflow

An automated **Procure-to-Pay (P2P)** workflow: purchase requests move from request to payment by themselves, and people only step in when a decision is needed.

> ⚠️ **Demo project only.** All departments, suppliers, requests and invoices are made-up data.

## 🔀 The workflow
```
📥 Request → ✅ Approval routing → 📄 Quote comparison → 🧾 Purchase order → 📦 Goods received → 🔍 Invoice 3-way match → 💸 Paid
```

| Step | What happens automatically |
|---|---|
| 📥 **Request** | AI reads messy purchase-request emails and turns them into structured data |
| 🚩 **Budget check** | Requests bigger than the department's remaining budget go to the Finance Director as exceptions |
| ✅ **Approval routing** | Under AED 5,000: auto-approved · up to 25,000: department manager · above: Finance Director |
| ⏰ **Reminders** | Approvers who don't reply get automatic reminders (sooner for urgent requests) |
| 📄 **Quote comparison** | Big purchases get 3 quotes, scored on price, delivery and supplier rating (best value, not just cheapest) |
| 🧾 **Purchase order** | Created automatically and sent to the chosen supplier |
| 🔍 **3-way match** | Invoice is paid only if **PO = goods received = invoice**; wrong invoices are blocked and the overpayment is stopped |

## 🖥️ The app
- **⚙️ Live Workflow:** a running simulation with a pipeline board, live activity log, KPI cards (auto-approvals, reminders, budget exceptions, blocked invoices, overpayment stopped) and department budget bars
- **🤖 AI Document Reader:** Gemini reads purchase-request emails, supplier quotes and invoices and extracts clean structured data (structured output with a fixed schema)
- **📋 Workflow Rules:** the business rules the workflow follows

## 💡 Business value
- Small purchases are approved instantly, with no waiting on people
- Managers only see the requests that really need them
- Budget overruns are caught **before** money is committed
- Billing errors (wrong price, short delivery) are caught **before** payment

## Tech stack
Python · pandas · Gemini API (structured output) · Pydantic · Plotly · Streamlit
