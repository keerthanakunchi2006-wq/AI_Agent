# Acceptance Scenarios — Supply Chain Disruption & Replanning

Five required scenarios with measurable results. Each is reproducible via the
dashboard or the API. Examples assume the API is running at
`http://localhost:8000` and you have logged in (`admin/admin123`).

> All supplier and purchase actions are **simulated/sandboxed**.

---

## Scenario 1 — A supplier delays a shipment; identify affected orders & products

**Trigger:** a purchase order passes its expected delivery date with no
actual arrival.

**API:**
```powershell
# monitor current delays (deterministic detection)
curl.exe http://localhost:8000/api/v1/disruptions/delays/monitor -H "Authorization: Bearer <TOKEN>"

# run the full agent workflow for a specific delayed PO
curl.exe -X POST http://localhost:8000/api/v1/disruptions/run `
  -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" `
  -d '{\"disruption\":{\"type\":\"supplier_delay\",\"severity\":\"high\",\"supplier_id\":3,\"po_id\":<PO_ID>,\"estimated_delay_days\":10}}'
```

**Dashboard:** *Dashboard* → delayed shipments KPI + Risk Alerts;
*Disruption Simulation* with type `supplier_delay`.

**Measurable results (returned by `/disruptions/run` → `impact_analysis`):**
- `affected_order_count` — open POs hit by the delay
- `affected_product_count` — distinct products on those POs
- `affected_po_ids` — exact PO list
- `committed_quantity` — total units at risk
- `at_risk_value` — total $ value at risk
- `inventory_gap[].shortfall` — per-product shortfall vs safety stock

---

## Scenario 2 — Inventory insufficient because of unexpected demand

**Trigger:** the Forecasting Agent predicts demand exceeding on-hand +
safety stock for a product.

**API:**
```powershell
curl.exe "http://localhost:8000/api/v1/forecasting/shortages?horizon_months=3" -H "Authorization: Bearer <TOKEN>"
```

**Dashboard:** *Demand Forecasting* view → "Predicted Shortages" panel.

**Measurable results:**
- `predicted_demand`, `on_hand` per product/period
- `is_shortage_risk = true` when predicted demand > 1.2 × on-hand
- 95% confidence bounds (`lower_bound`, `upper_bound`)
- Count of products at risk

---

## Scenario 3 — Original supplier unavailable; recommend alternatives

**Trigger:** a supplier becomes unavailable; the system must source from
others.

**API:**
```powershell
# ranked alternatives for a product, excluding the original supplier
curl.exe "http://localhost:8000/api/v1/recovery/alternatives?product_id=12&quantity=300&exclude_supplier_id=3" -H "Authorization: Bearer <TOKEN>"

# or run the workflow with type=supplier_unavailable
curl.exe -X POST http://localhost:8000/api/v1/disruptions/run `
  -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" `
  -d '{\"disruption\":{\"type\":\"supplier_unavailable\",\"severity\":\"critical\",\"supplier_id\":3,\"estimated_delay_days\":14}}'
```

**Dashboard:** *Supplier Comparison* view → pick product + exclude original.

**Measurable results (`alternative_suppliers`, sorted by `score`):**
- `unit_cost`, `transport_cost`, `total_cost`
- `lead_time_days`, `delivery_days`, `delay_vs_original`
- `on_time_rate`, `rating`
- composite `score` (cost 0.4 · delay 0.3 · reliability 0.2 · quality 0.1)

---

## Scenario 4 — Compare original vs optimised recovery plan (cost & delay)

**Trigger:** the Optimisation Agent builds both a single-supplier baseline and
an OR-Tools multi-supplier optimised plan.

**API:**
```powershell
# what-if comparison (no persisted workflow needed)
curl.exe -X POST http://localhost:8000/api/v1/simulations/what-if `
  -H "Content-Type: application/json" -H "Authorization: Bearer <TOKEN>" `
  -d '{\"type\":\"supplier_unavailable\",\"severity\":\"high\",\"supplier_id\":3,\"estimated_delay_days\":12}'

# compare a stored plan
curl.exe http://localhost:8000/api/v1/recovery/plans/<plan_id>/compare -H "Authorization: Bearer <TOKEN>"
```

**Dashboard:** *Disruption Simulation* → "Original Plan" vs "Optimized Plan"
cards; *Recovery Plans* → View.

**Measurable results:**
- `original_plan_cost` vs `optimized_plan_cost`
- `original_plan_delay_days` vs `optimized_plan_delay_days`
- `cost_savings = original − optimized`
- `delay_savings_days`
- `solver = "ortools"` (or `"greedy"` fallback)

---

## Scenario 5 — Request human approval for a proposed purchase change & track it

**Trigger:** the Approval Agent raises an `approval_request` when a plan
exceeds `APPROVAL_COST_THRESHOLD` ($25,000) or `APPROVAL_DELAY_THRESHOLD_DAYS`
(7 days). An approver signs off; the Tracking Agent records the decision.

**API:**
```powershell
# list pending approvals
curl.exe http://localhost:8000/api/v1/approvals/pending -H "Authorization: Bearer <TOKEN>"

# approve (requires approver/admin role)
curl.exe -X POST http://localhost:8000/api/v1/approvals/<id>/decide `
  -H "Content-Type: application/json" -H "Authorization: Bearer <APPROVER_TOKEN>" `
  -d '{\"status\":\"approved\",\"decided_by\":\"approver\",\"decision_note\":\"OK to proceed\"}'

# view the audit trail
curl.exe http://localhost:8000/api/v1/recovery/decisions?limit=50 -H "Authorization: Bearer <TOKEN>"
```

**Dashboard:** *Human Approval* view → Approve/Reject buttons;
*Decision Tracking* view → full history.

**Measurable results:**
- `approval_request` created with `status=pending`, `total_cost`,
  `total_delay_days`, `requested_at`
- after decision: `status=approved|rejected`, `decided_by`, `decided_at`,
  `decision_note`
- `decision_history` rows: `approval_requested`, `approval_approved`,
  `recovery_workflow_completed`, `progress_*`, `disruption_resolved`

---

## How the scenarios map to agents

| Scenario | Agents involved |
|---|---|
| 1 | Monitoring → Impact Analysis → Tracking |
| 2 | Forecasting → Impact Analysis → Tracking |
| 3 | Supplier Evaluation → Optimisation → Tracking |
| 4 | Monitoring → Impact Analysis → Forecasting → Supplier Evaluation → Optimisation → Tracking |
| 5 | Optimisation → Approval → Tracking |

Every scenario is also covered by automated tests in `backend/tests/`.
