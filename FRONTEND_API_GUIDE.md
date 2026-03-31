# 🏦 AI Personal Finance Analyzer — Frontend Developer Guide

> **Backend Base URL:** `http://localhost:8000`  
> **API Docs (Swagger):** `http://localhost:8000/docs`  
> **CORS:** `http://localhost:5173`, `http://localhost:3000`  
> **Auth:** Session-token based (returned after CSV upload)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Getting Started](#2-getting-started)
3. [Authentication Flow](#3-authentication-flow)
4. [API Endpoints Reference](#4-api-endpoints-reference)
   - [Upload](#41-upload)
   - [Analytics](#42-analytics)
   - [Insights](#43-insights)
5. [Category System](#5-category-system)
6. [Suggested Page Structure](#6-suggested-page-structure)
7. [UI Component Mapping](#7-ui-component-mapping)
8. [Error Handling](#8-error-handling)
9. [Sample API Responses](#9-sample-api-responses)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                       │
├─────────────────────────────────────────────────────────┤
│  Upload Page → Dashboard → Insights → Story → Simulate │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (JSON)
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (Python)                    │
├──────────┬──────────┬───────────────────────────────────┤
│  Upload  │Analytics │           Insights                │
│  Router  │ Router   │           Router                  │
├──────────┴──────────┴───────────────────────────────────┤
│  CSV Parser → Data Cleaner → Merchant Cleaner →         │
│  Categorizer (ML) → Transaction Structurer              │
├─────────────────────────────────────────────────────────┤
│  Analytics Engine  │  Momentum Engine  │  Simulator     │
│  Behavior Engine   │  Monthly Summary  │  Savings Ranker│
│  Micro-Spend Det.  │  Subscription Det │  Story Gen     │
│  Forecast Engine   │  Insights Engine  │                │
└─────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. User uploads CSV → backend returns `session_token`
2. Frontend stores `session_token` and passes it as query param to all subsequent requests
3. No user accounts, no cookies — token-based in-memory sessions

---

## 2. Getting Started

### Running the backend

```bash
cd finance-analyzer-backend
source venv/bin/activate
PYTHONPATH=. uvicorn server.main:app --reload --port 8000
```

### Frontend HTTP client setup

```typescript
const API_BASE = "http://localhost:8000";

// Store after upload
let sessionToken: string = "";

async function apiGet(path: string, params?: Record<string, string>) {
  const url = new URL(`${API_BASE}${path}`);
  url.searchParams.set("session_token", sessionToken);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

async function apiPost(path: string, body?: any) {
  const url = new URL(`${API_BASE}${path}`);
  url.searchParams.set("session_token", sessionToken);
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}
```

---

## 3. Authentication Flow

This backend uses **session tokens** — not JWT or OAuth. The token is returned after a CSV upload and must be passed as a query parameter to every subsequent request.

```
User uploads CSV
       │
       ▼
POST /api/upload/csv  (multipart/form-data)
       │
       ▼
Returns { session_token: "abc123..." }
       │
       ▼
Store in React state / context
       │
       ▼
All API calls: GET /api/analytics/summary?session_token=abc123...
```

> **Important:** Sessions are stored **in-memory**. If the backend restarts, all sessions are lost and the user must re-upload.

---

## 4. API Endpoints Reference

### 4.1 Upload

#### `POST /api/upload/csv`

Upload a bank statement CSV file. This triggers the full processing pipeline: parsing → cleaning → merchant normalization → ML categorization → structuring.

**Request:**
```
Content-Type: multipart/form-data
Body: file=<CSV file>
```

**Response:**
```json
{
  "session_token": "f7a3b2c1-8e4d-4a5f-b6c7-d8e9f0a1b2c3",
  "transactions_parsed": 247,
  "transactions_categorized": 231,
  "date_range": {
    "start": "2024-01-02",
    "end": "2024-03-28"
  },
  "message": "Successfully processed 247 transactions."
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Not a .csv file |
| 400 | Empty file |
| 400 | No valid transactions found |
| 413 | File > 10MB |
| 500 | Processing error |

**Frontend implementation:**
```typescript
async function uploadCSV(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/upload/csv`, {
    method: "POST",
    body: formData,
  });
  
  const data = await res.json();
  sessionToken = data.session_token; // Store globally
  return data;
}
```

---

### 4.2 Analytics

#### `GET /api/analytics/summary`

Core financial summary with KPIs, category breakdown, monthly spending, cash flow, and trends.

**Query params:** `session_token` (required)

**Response shape:**
```typescript
interface AnalyticsSummary {
  total_income: number;        // e.g. 201000.00
  total_expenses: number;      // e.g. 49159.00
  net_savings: number;         // e.g. 151841.00
  savings_rate: number;        // e.g. 75.5 (percentage)
  avg_daily_spend: number;     // e.g. 568.79
  top_category: string;        // e.g. "Shopping"
  transaction_count: number;   // e.g. 247
  date_range: {
    start: string;             // "2024-01-01"
    end: string;               // "2024-03-28"
  };
  monthly_spending: MonthlySpending[];
  category_breakdown: CategoryBreakdown[];
  cash_flow: CashFlowData[];
  trends: TrendData[];
}

interface MonthlySpending {
  month: string;               // "2024-01"
  total_debit: number;
  total_credit: number;
  net: number;
  transaction_count: number;
}

interface CategoryBreakdown {
  category: string;            // "Food & Dining"
  total: number;               // 15100.00
  percentage: number;          // 30.7
  count: number;               // 54
  icon: string;                // "🍔"
}

interface CashFlowData {
  month: string;
  income: number;
  expenses: number;
  net: number;
}

interface TrendData {
  period: string;              // "2024-01"
  value: number;               // monthly spending amount
  change_pct: number | null;   // MoM change %, null for first month
}
```

**Suggested UI:** KPI cards grid + donut chart (categories) + bar chart (monthly) + line chart (trends)

---

#### `GET /api/analytics/extended`

Rich analytics dataset for power dashboards. Includes everything in `/summary` plus per-category monthly trends, daily cash flow, rolling averages, and top merchants.

**Query params:** `session_token` (required)

**Response shape:**
```typescript
interface ExtendedAnalytics {
  kpis: {
    total_income: number;
    total_expenses: number;
    net_savings: number;
    savings_rate: number;        // percentage
    avg_daily_spend: number;
    transaction_count: number;
    debit_count: number;
    credit_count: number;
    date_range: { start: string; end: string };
  };

  category_breakdown: {
    category: string;
    total: number;
    percentage: number;
    count: number;
    avg_transaction: number;
    icon: string;
    top_merchants: {
      merchant: string;
      total: number;
      count: number;
    }[];
  }[];

  monthly_trends: {
    month: string;               // "2024-01"
    spend: number;
    income: number;
    savings: number;
    savings_rate: number;
    transaction_count: number;
    spend_change_pct: number | null;
    income_change_pct: number | null;
    savings_change_pct: number | null;
  }[];

  // For stacked area/bar charts — each entry has month + per-category spend
  category_trends: {
    month: string;
    total: number;
    [categoryName: string]: number | string;  // dynamic keys
    // e.g. "Food & Dining": 5284.31, "Shopping": 8653.71
  }[];

  daily_cash_flow: {
    date: string;                // "2024-01-15"
    income: number;
    expense: number;
    net: number;
    cumulative_income: number;
    cumulative_expense: number;
    cumulative_net: number;
    transaction_count: number;
  }[];

  rolling_averages: {
    monthly: {
      month: string;
      actual_spend: number;
      rolling_3m_avg: number;
      rolling_6m_avg: number;
      deviation_from_3m: number;
    }[];
    current_3m_avg: number;
    current_6m_avg: number;
  };

  top_merchants: {
    merchant: string;
    total: number;
    percentage: number;
    count: number;
    avg_transaction: number;
    category: string;
    icon: string;
  }[];
}
```

**Suggested UI:**
- Stacked area chart → `category_trends`
- Line chart with bands → `rolling_averages`
- Cumulative line chart → `daily_cash_flow`
- Merchant table → `top_merchants`

---

#### `GET /api/analytics/transactions`

Paginated, filterable transaction list.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_token` | string | required | Session token |
| `page` | int | 1 | Page number |
| `per_page` | int | 50 | Items per page (max 200) |
| `category` | string | null | Filter by category |
| `transaction_type` | string | null | Filter: "credit" or "debit" |

**Response shape:**
```typescript
interface TransactionListResponse {
  transactions: {
    id: string;
    date: string;               // "2024-01-15"
    time_hour: number | null;   // 0-23
    description_clean: string;
    amount: number;
    transaction_type: "credit" | "debit";
    category: string;
    merchant_clean: string | null;
    is_recurring: boolean;
  }[];
  total: number;
  page: number;
  per_page: number;
}
```

**Suggested UI:** Data table with pagination, column sorting, category filter chips

---

### 4.3 Insights

#### `GET /api/insights/behavioral`

All-in-one behavioral insights including spending personality, anomalies, and financial momentum.

**Response shape:**
```typescript
interface BehavioralInsights {
  insights: {
    title: string;               // "Weekend Overspender"
    description: string;
    severity: "info" | "warning" | "critical";
    icon: string;                // "🌙"
    value: string | null;        // "₹2,450"
    recommendation: string;
  }[];

  micro_spending: {
    merchant: string;
    frequency: number;
    total_amount: number;
    avg_amount: number;
    category: string;
  }[];

  subscriptions: {
    merchant: string;
    amount: number;
    frequency: "monthly" | "weekly" | "quarterly" | "yearly";
    confidence: number;          // 0.0–1.0
    category: string;
    is_hidden: boolean;
  }[];

  personality: {
    type: string;                // "Balanced Spender"
    description: string;
    strengths: string[];
    risks: string[];
    icon: string;                // "⚖️"
  };

  momentum: {
    direction: "improving" | "stable" | "declining";
    score: number;               // -1.0 to 1.0
    description: string;
    factors: string[];
  };

  savings_opportunities: {
    category: string;
    current_spend: number;
    potential_saving: number;
    difficulty: "easy" | "moderate" | "hard";
    suggestion: string;
  }[];

  anomalies: {
    date: string;
    description: string;
    amount: number;
    category: string;
    reason: string;              // "Amount 3.2x above category average"
    severity: "low" | "medium" | "high";
  }[];
}
```

**Suggested UI:** Insight cards with severity-colored borders + personality badge + anomaly timeline

---

#### `GET /api/insights/behavior-patterns`

Detailed spending patterns by day-of-week and time-of-day.

**Response shape:**
```typescript
interface BehaviorPatterns {
  day_of_week: {
    per_day: {
      day_index: number;         // 0=Monday, 6=Sunday
      day_name: string;          // "Monday"
      day_short: string;         // "Mon"
      total_spend: number;
      transaction_count: number;
      avg_amount: number;
      is_weekend: boolean;
    }[];
    peak_day: string;            // "Thursday"
    peak_day_total: number;
    weekend_vs_weekday: {
      weekend_total: number;
      weekday_total: number;
      weekend_transaction_count: number;
      weekday_transaction_count: number;
      weekend_avg_per_transaction: number;
      weekday_avg_per_transaction: number;
      weekend_avg_per_day: number;
      weekday_avg_per_day: number;
      overspend_pct: number;     // positive = weekends higher
      is_overspending: boolean;
    };
  };

  time_of_day: {
    hourly_heatmap: {            // 24 entries (0-23)
      hour: number;
      label: string;             // "13:00"
      total_spend: number;
      transaction_count: number;
      avg_amount: number;
    }[];
    time_bands: {
      band: string;              // "Morning (6-12)"
      total_spend: number;
      transaction_count: number;
      avg_amount: number;
    }[];
    peak_hour: number;
    peak_hour_total: number;
    late_night: {
      total_spend: number;
      transaction_count: number;
      percent_of_total: number;
      severity: "none" | "mild" | "moderate" | "severe";
    };
  };

  insights: {
    key: string;
    title: string;
    description: string;
    severity: "info" | "warning" | "critical";
    icon: string;
  }[];
}
```

**Suggested UI:**
- Bar chart → `per_day` spending
- Heatmap grid → `hourly_heatmap` (24 columns × 7 rows ideally, or single-row)
- Weekend vs weekday comparison card
- Late-night spending alert card

---

#### `GET /api/insights/monthly-summary`

Per-month financial snapshots with month-over-month comparison.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_token` | string | required | |
| `month` | string | null | Target month "YYYY-MM", defaults to latest |

**Response shape:**
```typescript
interface MonthlySummaryResponse {
  months: {
    month: string;               // "2024-01"
    total_spend: number;
    total_income: number;
    net_savings: number;
    savings_rate: number;
    transaction_count: number;
    debit_count: number;
    credit_count: number;
    avg_daily_spend: number;
    date_range: { start: string; end: string };
    categories: {
      category: string;
      total: number;
      count: number;
      percentage: number;
      icon: string;
    }[];
    top_merchants: {
      merchant: string;
      total: number;
      count: number;
    }[];
    vs_previous: {               // null for first month
      spend_change: number;      // absolute ₹ change
      spend_change_pct: number;  // percentage change
      income_change: number;
      savings_change: number;
      status: "improved" | "declined" | "stable";
      biggest_category_changes: {
        category: string;
        change: number;
        change_pct: number;
        direction: "up" | "down";
      }[];
    } | null;
  }[];

  overview: {
    total_months: number;
    avg_monthly_spend: number;
    avg_monthly_income: number;
    avg_monthly_savings: number;
    total_spend: number;
    total_income: number;
    total_savings: number;
    best_month: {
      month: string;
      savings: number;
      savings_rate: number;
    };
    worst_month: {
      month: string;
      savings: number;
      savings_rate: number;
    };
    spending_trend: {
      direction: "increasing" | "decreasing" | "stable";
      slope_pct_per_month: number;
      description: string;
    };
  };
}
```

**Suggested UI:** Month selector tabs + KPI cards + category donut + MoM comparison arrows

---

#### `GET /api/insights/momentum`

Financial momentum score with trend analysis.

**Response shape:**
```typescript
interface FinancialMomentumResponse {
  score: number;                 // -100 to +100
  direction: "improving" | "stable" | "declining";

  monthly_momentum: {
    month: string;
    spend: number;
    rolling_3m_avg: number;
    mom_change: number | null;
    mom_change_pct: number | null;
    deviation_from_avg: number;
    is_above_average: boolean;
  }[];

  savings_momentum: {
    monthly: {
      month: string;
      savings_rate: number;
      income: number;
      expense: number;
      savings: number;
    }[];
    current_rate: number;
    avg_rate: number;
    trend: "improving" | "stable" | "declining";
  };

  category_momentum: {
    category: string;
    direction: "increasing" | "stable" | "decreasing";
    current_monthly: number;
    previous_monthly: number;
    mom_change: number;
    mom_change_pct: number;
    avg_monthly: number;
    trend_slope: number;         // % change per month
  }[];

  factors: string[];             // Human-readable list
  recommendation: string;
}
```

**Suggested UI:**
- Large gauge/dial → `score` (-100 to +100)
- Direction badge → `direction`
- Line chart with 3M band → `monthly_momentum`
- Category arrows table → `category_momentum` (↑/→/↓ icons)
- Factors list → `factors`

---

#### `GET /api/insights/micro-spending`

Detect small transactions that silently drain money.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_token` | string | required | |
| `threshold` | float | 300 | Max ₹ amount to consider "micro" (50-1000) |

**Response shape:**
```typescript
interface MicroSpendingResponse {
  merchants: {
    merchant: string;
    count: number;
    total_amount: number;
    avg_amount: number;
    min_amount: number;
    max_amount: number;
    category: string;
    drain_rank: number;          // 1 = biggest drain
  }[];

  summary: {
    total_micro_spend: number;
    total_transactions: number;
    avg_transaction: number;
    percent_of_total_spending: number;
    monthly_average: number;
    yearly_projection: number;
    unique_merchants: number;
    threshold: number;
  };

  recommendations: {
    type: "critical" | "warning" | "info" | "tip";
    title: string;
    description: string;
    action: string;
  }[];
}
```

**Suggested UI:** Ranked merchant list + "money drain" visualization + yearly projection card

---

#### `GET /api/insights/subscriptions`

Detect recurring payments — both known and hidden subscriptions.

**Response shape:**
```typescript
interface SubscriptionResponse {
  subscriptions: {
    merchant: string;
    avg_amount: number;
    frequency: "monthly" | "weekly" | "quarterly" | "yearly";
    confidence: number;          // 0.0–1.0
    status: "known" | "hidden";
    category: string;
    occurrences: number;
    total_spent: number;
    monthly_cost: number;
    annual_cost: number;
  }[];

  hidden_subscriptions: { /* same shape */ }[];

  summary: {
    total_subscriptions: number;
    known_subscriptions: number;
    hidden_subscriptions: number;
    total_monthly_cost: number;
    total_annual_cost: number;
  };
}
```

**Suggested UI:** Subscription cards (known + hidden with alert styling) + total monthly/annual cost

---

#### `POST /api/insights/simulate`

What-if simulator — project savings under different reduction scenarios.

**Query params:** `session_token` (required)

**Request body (optional):**
```json
[
  { "category": "Food & Dining", "reduction_pct": 20 },
  { "category": "Shopping", "reduction_amount": 2000 },
  { "category": "all", "reduction_pct": 10 }
]
```

> If body is `null` or empty, the backend auto-generates smart default scenarios based on actual spending patterns.

**Response shape:**
```typescript
interface SimulatorResponse {
  individual_scenarios: {
    label: string;               // "Reduce Food & Dining by 20%"
    category: string;
    reduction_pct: number;
    reduction_amount: number;
    current_monthly: number;
    projected_monthly: number;
    monthly_savings: number;
    yearly_savings: number;
    projections: {
      "3_months": number;
      "6_months": number;
      "12_months": number;
    };
    category_current: number;    // current monthly for this category
  }[];

  combined_scenario: {
    label: string;               // "All reductions combined"
    current_monthly: number;
    projected_monthly: number;
    monthly_savings: number;
    yearly_savings: number;
    projections: {
      "3_months": number;
      "6_months": number;
      "12_months": number;
    };
    breakdown: {
      category: string;
      monthly_saving: number;
    }[];
  };

  summary: {
    current_monthly_spend: number;
    scenarios_analyzed: number;
    max_yearly_savings: number;
    combined_yearly_savings: number;
  };
}
```

**Suggested UI:**
- Scenario builder with sliders (per category)
- Comparison bar chart (current vs projected)
- Combined savings counter with 3/6/12 month tabs
- "Create custom scenario" form

---

#### `GET /api/insights/savings-opportunities`

Ranked categories by savings potential.

**Response shape:**
```typescript
interface SavingsOpportunitiesResponse {
  opportunities: {
    rank: number;                // 1 = best opportunity
    category: string;
    icon: string;
    monthly_spend: number;
    pct_of_total_spend: number;
    transaction_count: number;
    avg_transaction: number;
    difficulty: "easy" | "moderate" | "hard";
    difficulty_score: number;    // 1=easy, 2=moderate, 3=hard
    tip: string;                 // Actionable advice
    projections: {
      conservative_10pct: { monthly: number; yearly: number };
      moderate_20pct: { monthly: number; yearly: number };
      aggressive_30pct: { monthly: number; yearly: number };
      recommended: { monthly: number; yearly: number; reduction_pct: number };
    };
    top_merchants: {
      merchant: string;
      monthly_spend: number;
      count: number;
    }[];
    opportunity_score: number;   // Higher = better opportunity
  }[];

  quick_wins: {
    category: string;
    icon: string;
    tip: string;
    monthly_spend: number;
    potential_monthly_saving: number;
    potential_yearly_saving: number;
  }[];

  summary: {
    total_monthly_spend_analyzed: number;
    total_monthly_spend: number;
    total_categories: number;
    recommended_monthly_saving: number;
    recommended_yearly_saving: number;
    max_monthly_saving: number;
    max_yearly_saving: number;
    recommended_saving_pct: number;
  };
}
```

**Suggested UI:**
- Ranked opportunity cards with difficulty badges (🟢 easy / 🟡 moderate / 🔴 hard)
- Quick wins section at top (highlighted)
- Projection bars (10% / 20% / 30%)
- Total potential savings counter

---

#### `GET /api/insights/forecast`

Spend forecast for the next N months.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_token` | string | required | |
| `months` | int | 3 | Months to forecast (1-12) |

**Response shape:**
```typescript
type ForecastResponse = {
  month: string;                 // "2024-04"
  predicted_spending: number;
  lower_bound: number;           // 95% CI lower
  upper_bound: number;           // 95% CI upper
  confidence: number;            // 0.0–1.0
}[];
```

**Suggested UI:** Line chart with confidence interval band (shaded area between lower/upper bounds)

---

#### `GET /api/insights/story`

Human-readable monthly financial narrative.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_token` | string | required | |
| `month` | string | null | Target month "YYYY-MM", defaults to latest |

**Response shape:**
```typescript
interface StoryResponse {
  title: string;                 // "🏆 March 2024 — You Absolutely Crushed It!"
  month: string;                 // "2024-03"
  month_label: string;           // "March 2024"
  summary: string;               // Opening paragraph

  sections: {
    heading: string;             // "Where Your Money Went"
    icon: string;                // "📦"
    content: string;             // Markdown-safe paragraph
  }[];

  highlights: string[];          // "💪 Outstanding savings rate of 75.1%"
  concerns: string[];            // "⚠️ Savings rate is below 10%"
  tips: string[];                // "💡 Adopt the 50/30/20 rule"

  score: number;                 // 0-100 financial health score
  tone: "celebratory" | "encouraging" | "neutral" | "concerned";

  stats: {
    total_income: number;
    total_spent: number;
    net_savings: number;
    savings_rate: number;
    transaction_count: number;
  };
}
```

**Suggested UI:**
- Story card with `title` as heading
- Health score gauge (0-100, color-coded by `tone`)
- Sections rendered as paragraphs with icons
- Highlights (🟢), concerns (🔴), tips (🔵) in card columns
- Month navigator

---

#### `GET /api/health`

Backend health check.

**Response:**
```json
{
  "status": "healthy",
  "service": "AI Personal Finance Analyzer",
  "version": "1.0.0"
}
```

---

## 5. Category System

The backend uses these fixed categories, each with an emoji icon:

| Category | Icon | Reducible? |
|----------|------|------------|
| Food & Dining | 🍔 | ✅ Easy |
| Groceries | 🛒 | ✅ Moderate |
| Transport | 🚗 | ✅ Moderate |
| Shopping | 🛍️ | ✅ Moderate |
| Entertainment | 🎬 | ✅ Easy |
| Bills & Utilities | 💡 | ✅ Moderate |
| Rent & Housing | 🏠 | ❌ |
| Health & Medical | 🏥 | ⚠️ Hard |
| Education | 📚 | ⚠️ Hard |
| Insurance | 🛡️ | ❌ |
| Investment | 📈 | ❌ |
| EMI & Loans | 🏦 | ❌ |
| Transfer | 💸 | ❌ |
| ATM & Cash | 🏧 | ❌ |
| Subscriptions | 📦 | ✅ Easy |
| Travel | ✈️ | ✅ Moderate |
| Personal Care | 💇 | ✅ Easy |
| Gifts & Donations | 🎁 | ✅ Easy |
| Salary | 💰 | — (income) |
| Refund | 🔄 | — (income) |
| Interest | 💵 | — (income) |
| Uncategorized | ❓ | — |

> Use the `icon` field from API responses directly — don't hardcode icons on frontend.

---

## 6. Suggested Page Structure

```
App
├── 📄 Landing / Upload Page
│   ├── Drag-and-drop CSV upload zone
│   ├── Supported format info
│   └── Processing animation
│
├── 📊 Dashboard (after upload)
│   ├── KPI Cards Row (income, expenses, savings, savings rate)
│   ├── Monthly Trend Chart (bar + line)
│   ├── Category Breakdown (donut chart)
│   ├── Cash Flow Chart
│   └── Top Merchants Table
│
├── 💡 Insights Page
│   ├── Tab: Behavior Patterns
│   │   ├── Day-of-week bar chart
│   │   ├── Time-of-day heatmap
│   │   └── Weekend vs weekday comparison
│   │
│   ├── Tab: Financial Momentum
│   │   ├── Score gauge (-100 to +100)
│   │   ├── Spending trend with rolling average
│   │   ├── Category momentum arrows table
│   │   └── Factors list
│   │
│   ├── Tab: Subscriptions & Micro-spending
│   │   ├── Subscription cards
│   │   ├── Hidden subscription alerts
│   │   └── Micro-spend merchant drain ranking
│   │
│   └── Tab: Anomalies
│       └── Timeline of unusual transactions
│
├── 💰 Savings Page
│   ├── Quick Wins section (top 3 easy savings)
│   ├── Ranked Opportunity Cards
│   ├── What-If Simulator
│   │   ├── Category sliders (% reduction)
│   │   ├── Before/after comparison
│   │   └── Projected savings timeline
│   └── Forecast Chart (with confidence bands)
│
├── 📖 Story Page
│   ├── Month selector
│   ├── Story title + health gauge
│   ├── Narrative sections
│   ├── Highlights / Concerns / Tips columns
│   └── Stats summary card
│
└── 📋 Transactions Page
    ├── Filterable data table
    ├── Category filter chips
    ├── Pagination
    └── CSV export (client-side)
```

---

## 7. UI Component Mapping

| Backend Data | Chart Type | Library Suggestion |
|-------------|------------|-------------------|
| `category_breakdown` | Donut / Pie chart | Recharts `PieChart` |
| `monthly_trends` | Grouped bar chart | Recharts `BarChart` |
| `category_trends` | Stacked area chart | Recharts `AreaChart` |
| `daily_cash_flow` | Line chart (cumulative) | Recharts `LineChart` |
| `rolling_averages` | Line chart with bands | Recharts `ComposedChart` |
| `hourly_heatmap` | Heatmap grid | Custom CSS grid or `react-calendar-heatmap` |
| `per_day` (behavior) | Bar chart | Recharts `BarChart` |
| `forecast` | Line with confidence band | Recharts `AreaChart` (shaded) |
| `momentum.score` | Gauge / speedometer | Custom SVG or `react-gauge-chart` |
| Transactions table | Data table | TanStack Table or AG Grid |
| What-If sliders | Range sliders | `rc-slider` or `@radix-ui/slider` |

---

## 8. Error Handling

All errors return this shape:

```json
{
  "detail": "Session not found. Please upload a CSV first."
}
```

**Key error codes:**

| Status | Meaning | Frontend Action |
|--------|---------|-----------------|
| 400 | Bad request (invalid file, empty, etc.) | Show error toast |
| 404 | Session not found | Redirect to upload page |
| 413 | File too large | Show file size limit message |
| 500 | Server error | Show generic error + retry button |

**Suggested error handler:**
```typescript
async function handleApiError(res: Response) {
  if (res.status === 404) {
    // Session expired — redirect to upload
    router.push("/upload");
    return;
  }
  const { detail } = await res.json();
  toast.error(detail || "Something went wrong");
}
```

---

## 9. Sample API Responses

### Upload → then Dashboard flow

```
1. POST /api/upload/csv        → { session_token: "abc..." }
2. GET  /api/analytics/summary → { total_income: 201000, ... }
3. GET  /api/analytics/extended → { kpis: {...}, category_trends: [...] }
4. GET  /api/insights/story    → { title: "🏆 March 2024 — ..." }
```

### Savings flow

```
1. GET  /api/insights/savings-opportunities → ranked opportunities
2. GET  /api/insights/micro-spending        → latte factor analysis
3. POST /api/insights/simulate             → what-if projections
4. GET  /api/insights/forecast?months=6    → future spend prediction
```

### Deep insights flow

```
1. GET /api/insights/behavioral       → personality + anomalies
2. GET /api/insights/behavior-patterns → day/time heatmap
3. GET /api/insights/momentum          → financial health score
4. GET /api/insights/monthly-summary   → per-month deep dive
5. GET /api/insights/subscriptions     → recurring payment audit
```

---

## Quick Reference — All Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload/csv` | Upload CSV, get session token |
| `GET` | `/api/analytics/summary` | Core financial KPIs |
| `GET` | `/api/analytics/extended` | Rich analytics (trends, rolling avgs) |
| `GET` | `/api/analytics/transactions` | Paginated transaction list |
| `GET` | `/api/insights/behavioral` | All-in-one behavioral insights |
| `GET` | `/api/insights/behavior-patterns` | Day/time spending patterns |
| `GET` | `/api/insights/monthly-summary` | Per-month snapshots + MoM |
| `GET` | `/api/insights/momentum` | Financial momentum score |
| `GET` | `/api/insights/micro-spending` | Small transaction detection |
| `GET` | `/api/insights/subscriptions` | Recurring payment detection |
| `POST` | `/api/insights/simulate` | What-if savings simulator |
| `GET` | `/api/insights/savings-opportunities` | Ranked savings potential |
| `GET` | `/api/insights/forecast` | Spending forecast |
| `GET` | `/api/insights/story` | Monthly financial narrative |
| `GET` | `/api/health` | Health check |

---

*Generated for AI Personal Finance Analyzer backend v1.0.0*  
*Last updated: 2026-03-31*
