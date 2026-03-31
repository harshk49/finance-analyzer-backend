# 🧪 Postman Testing Guide — AI Personal Finance Analyzer

> **Base URL:** `http://localhost:8000`  
> **Server Status:** The server is already running on port 8000.  
> If you need to restart: `source venv/bin/activate && PYTHONPATH=. uvicorn server.main:app --reload --port 8000`

---

## Quick Start (3 Steps)

```
Step 1:  POST /api/upload/csv         → Get session_token
Step 2:  Copy session_token
Step 3:  Use it in ALL subsequent GET/POST requests as ?session_token=xxx
```

---

## Mock CSV File

Use the file at: `mock_bank_statement.csv` (in project root)

It contains **90 transactions across 3 months** (Jan–Mar 2024):
- 3 salary credits (₹65K, ₹68K, ₹70K)
- Swiggy orders (frequent, ₹130–450)
- Amazon/Flipkart/Myntra shopping
- Uber rides, petrol
- Netflix, Spotify subscriptions  
- BigBasket, Blinkit, Zepto groceries
- Starbucks, PVR, BookMyShow
- 1 Flipkart refund

---

## API Testing Sequence

### ✅ Step 1: Health Check

```
GET http://localhost:8000/api/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "service": "AI Personal Finance Analyzer",
  "version": "1.0.0"
}
```

---

### ✅ Step 2: Upload CSV (START HERE)

```
POST http://localhost:8000/api/upload/csv
```

**Postman setup:**
1. Method: `POST`
2. Go to **Body** tab
3. Select **form-data**
4. Key: `file` (change type dropdown to **File**)
5. Value: Select `mock_bank_statement.csv`
6. Hit **Send**

**Expected response:**
```json
{
  "session_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "transactions_parsed": 90,
  "transactions_categorized": 85,
  "date_range": {
    "start": "2024-01-01",
    "end": "2024-03-31"
  },
  "message": "Successfully processed 90 transactions."
}
```

> ⚠️ **COPY the `session_token`!** You need it for EVERY request below.

---

### ✅ Step 3: Set Up Postman Variable (Optional but Recommended)

In Postman:
1. Go to **Environments** → Create "Finance Analyzer"
2. Add variable: `session_token` = (paste your token)
3. Add variable: `base_url` = `http://localhost:8000`
4. In all URLs below, use: `{{base_url}}/api/...?session_token={{session_token}}`

---

## 📊 Analytics Endpoints

### 3.1 Analytics Summary

```
GET http://localhost:8000/api/analytics/summary?session_token=YOUR_TOKEN
```

Returns: KPIs (income, expenses, savings rate), category breakdown, monthly trends, cash flow.

---

### 3.2 Extended Analytics

```
GET http://localhost:8000/api/analytics/extended?session_token=YOUR_TOKEN
```

Returns: Everything in summary PLUS per-category monthly trends, daily cash flow, rolling averages, top merchants.

---

### 3.3 Transaction List (with pagination & filters)

```
GET http://localhost:8000/api/analytics/transactions?session_token=YOUR_TOKEN&page=1&per_page=20
```

**Optional filters:**
```
GET ...&category=Food%20%26%20Dining
GET ...&transaction_type=debit
GET ...&category=Shopping&page=1&per_page=10
```

---

## 💡 Insights Endpoints

### 4.1 Behavioral Insights (All-in-one)

```
GET http://localhost:8000/api/insights/behavioral?session_token=YOUR_TOKEN
```

Returns: Spending personality, anomalies, momentum, micro-spending alerts, subscription detection, savings opportunities.

---

### 4.2 Behavior Patterns

```
GET http://localhost:8000/api/insights/behavior-patterns?session_token=YOUR_TOKEN
```

Returns: Day-of-week breakdown, hourly heatmap (24h), weekend vs weekday comparison, late-night spending detection.

---

### 4.3 Monthly Summary

```
GET http://localhost:8000/api/insights/monthly-summary?session_token=YOUR_TOKEN
```

Returns all months. To get a specific month:

```
GET http://localhost:8000/api/insights/monthly-summary?session_token=YOUR_TOKEN&month=2024-02
```

---

### 4.4 Financial Momentum

```
GET http://localhost:8000/api/insights/momentum?session_token=YOUR_TOKEN
```

Returns: Score (-100 to +100), direction, rolling averages, per-category momentum, factors.

---

### 4.5 Micro-Spending Detection

```
GET http://localhost:8000/api/insights/micro-spending?session_token=YOUR_TOKEN
```

With custom threshold:
```
GET http://localhost:8000/api/insights/micro-spending?session_token=YOUR_TOKEN&threshold=500
```

---

### 4.6 Subscription Detection

```
GET http://localhost:8000/api/insights/subscriptions?session_token=YOUR_TOKEN
```

Returns: Known + hidden subscriptions, monthly/annual cost summary.

---

### 4.7 What-If Simulator

#### Auto-generated scenarios:
```
POST http://localhost:8000/api/insights/simulate?session_token=YOUR_TOKEN
```
(No body needed — backend auto-generates smart scenarios)

#### Custom scenarios:
```
POST http://localhost:8000/api/insights/simulate?session_token=YOUR_TOKEN
Content-Type: application/json

[
  {"category": "Food & Dining", "reduction_pct": 25},
  {"category": "Shopping", "reduction_pct": 30},
  {"category": "Transport", "reduction_amount": 1000}
]
```

#### More scenario examples:
```json
// Reduce everything by 10%
[{"category": "all", "reduction_pct": 10}]

// Cut specific amount from entertainment
[{"category": "Entertainment", "reduction_amount": 500}]

// Multiple categories
[
  {"category": "Food & Dining", "reduction_pct": 20},
  {"category": "Shopping", "reduction_pct": 15},
  {"category": "Entertainment", "reduction_pct": 50},
  {"category": "Transport", "reduction_amount": 500}
]
```

---

### 4.8 Savings Opportunity Ranking

```
GET http://localhost:8000/api/insights/savings-opportunities?session_token=YOUR_TOKEN
```

Returns: Ranked categories by saving potential, quick wins, 3-level projections (10%/20%/30%).

---

### 4.9 Spending Forecast

```
GET http://localhost:8000/api/insights/forecast?session_token=YOUR_TOKEN&months=6
```

Options: `months=1` to `months=12`

---

### 4.10 Financial Story

```
GET http://localhost:8000/api/insights/story?session_token=YOUR_TOKEN
```

For a specific month:
```
GET http://localhost:8000/api/insights/story?session_token=YOUR_TOKEN&month=2024-01
```

---

## 📋 Complete Postman Collection (Copy-Paste URLs)

Replace `YOUR_TOKEN` with your actual session token:

```
1.  GET  http://localhost:8000/api/health
2.  POST http://localhost:8000/api/upload/csv                                          [form-data: file]
3.  GET  http://localhost:8000/api/analytics/summary?session_token=YOUR_TOKEN
4.  GET  http://localhost:8000/api/analytics/extended?session_token=YOUR_TOKEN
5.  GET  http://localhost:8000/api/analytics/transactions?session_token=YOUR_TOKEN&page=1&per_page=20
6.  GET  http://localhost:8000/api/insights/behavioral?session_token=YOUR_TOKEN
7.  GET  http://localhost:8000/api/insights/behavior-patterns?session_token=YOUR_TOKEN
8.  GET  http://localhost:8000/api/insights/monthly-summary?session_token=YOUR_TOKEN
9.  GET  http://localhost:8000/api/insights/momentum?session_token=YOUR_TOKEN
10. GET  http://localhost:8000/api/insights/micro-spending?session_token=YOUR_TOKEN
11. GET  http://localhost:8000/api/insights/subscriptions?session_token=YOUR_TOKEN
12. POST http://localhost:8000/api/insights/simulate?session_token=YOUR_TOKEN           [JSON body]
13. GET  http://localhost:8000/api/insights/savings-opportunities?session_token=YOUR_TOKEN
14. GET  http://localhost:8000/api/insights/forecast?session_token=YOUR_TOKEN&months=3
15. GET  http://localhost:8000/api/insights/story?session_token=YOUR_TOKEN
```

---

## 🔥 Quick Test with cURL

If you prefer terminal testing:

```bash
# 1. Upload CSV and capture token
TOKEN=$(curl -s -F "file=@mock_bank_statement.csv" http://localhost:8000/api/upload/csv | python3 -c "import sys,json; print(json.load(sys.stdin)['session_token'])")
echo "Token: $TOKEN"

# 2. Analytics summary
curl -s "http://localhost:8000/api/analytics/summary?session_token=$TOKEN" | python3 -m json.tool

# 3. Extended analytics
curl -s "http://localhost:8000/api/analytics/extended?session_token=$TOKEN" | python3 -m json.tool

# 4. Financial story
curl -s "http://localhost:8000/api/insights/story?session_token=$TOKEN" | python3 -m json.tool

# 5. Momentum
curl -s "http://localhost:8000/api/insights/momentum?session_token=$TOKEN" | python3 -m json.tool

# 6. Savings opportunities
curl -s "http://localhost:8000/api/insights/savings-opportunities?session_token=$TOKEN" | python3 -m json.tool

# 7. What-if simulator (auto scenarios)
curl -s -X POST "http://localhost:8000/api/insights/simulate?session_token=$TOKEN" | python3 -m json.tool

# 8. What-if simulator (custom)
curl -s -X POST "http://localhost:8000/api/insights/simulate?session_token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"category":"Food & Dining","reduction_pct":25},{"category":"Shopping","reduction_pct":30}]' | python3 -m json.tool

# 9. Forecast
curl -s "http://localhost:8000/api/insights/forecast?session_token=$TOKEN&months=6" | python3 -m json.tool

# 10. All behavioral insights
curl -s "http://localhost:8000/api/insights/behavioral?session_token=$TOKEN" | python3 -m json.tool
```

---

## ⚠️ Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `"Session not found"` (404) | Token expired or server restarted | Re-upload CSV |
| `"Only CSV files are accepted"` (400) | Wrong file type | Use `.csv` file |
| `"Address already in use"` | Port 8000 occupied | Kill: `lsof -ti:8000 \| xargs kill -9` |
| `"File is empty"` (400) | Empty CSV | Use the mock file provided |

---

## 💡 Swagger UI Alternative

You can also test everything directly in the browser:

```
http://localhost:8000/docs
```

This opens the interactive Swagger UI where you can try all endpoints without Postman.
