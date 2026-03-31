"""Monthly Story Generator — human-readable financial narratives.

Generates template-based stories WITHOUT an LLM. Each story is assembled
from modular narrative blocks that adapt dynamically to the data:

  §1  Opening headline + financial health emoji
  §2  Executive summary (income, spend, savings in natural language)
  §3  Spending breakdown narrative (top categories woven into prose)
  §4  Month-over-month trend narrative
  §5  Merchant spotlight (top merchants, emerging ones)
  §6  Behavioral observations (weekend/late-night/micro patterns)
  §7  Highlights (positive signals)
  §8  Concerns (warning signals)
  §9  Tips (actionable advice)
  §10 Financial health score (0-100)

The tone shifts based on financial health:
  85+  → celebratory
  60-84 → encouraging
  40-59 → neutral/advisory
  <40  → concerned/urgent
"""
import logging
import random
from typing import Optional

import numpy as np
import pandas as pd

from server.utils.constants import CATEGORY_ICONS

logger = logging.getLogger(__name__)


# ── Month names ─────────────────────────────────────────────────────
_MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


def _month_label(period_str: str) -> str:
    """Convert '2024-03' → 'March 2024'."""
    parts = period_str.split("-")
    if len(parts) == 2:
        return f"{_MONTH_NAMES.get(parts[1], parts[1])} {parts[0]}"
    return period_str


# ── Title templates (indexed by tone) ───────────────────────────────
_TITLES = {
    "celebratory": [
        "🏆 {month} — You Absolutely Crushed It!",
        "🌟 {month} — A Stellar Month for Your Wallet",
        "💎 {month} — Financial Discipline at Its Finest",
    ],
    "encouraging": [
        "✅ {month} — Solid Progress, Keep It Going",
        "📈 {month} — Good Momentum This Month",
        "👏 {month} — Your Finances Are on Track",
    ],
    "neutral": [
        "📊 {month} — Room for Improvement",
        "📋 {month} — Your Monthly Financial Snapshot",
        "🔍 {month} — Let's Break Down the Numbers",
    ],
    "concerned": [
        "⚠️ {month} — Your Finances Need Attention",
        "🚨 {month} — Spending Outpaced Comfort Zone",
        "📉 {month} — Time to Course-Correct",
    ],
}

# ── Summary opening templates ───────────────────────────────────────
_SUMMARY_OPENERS = {
    "celebratory": [
        "What a month! You brought in ₹{income} and kept spending at just ₹{spent}.",
        "Impressive control this month — ₹{income} earned, only ₹{spent} spent.",
    ],
    "encouraging": [
        "A productive month: ₹{income} came in and ₹{spent} went out.",
        "Your earnings of ₹{income} outpaced spending of ₹{spent} — nice work.",
    ],
    "neutral": [
        "This month you earned ₹{income} and spent ₹{spent} across {txn_count} transactions.",
        "Let's look at the numbers: ₹{income} in, ₹{spent} out, {txn_count} transactions total.",
    ],
    "concerned": [
        "A challenging month — ₹{income} earned but ₹{spent} spent.",
        "The numbers tell a story: ₹{income} income vs ₹{spent} in expenses.",
    ],
}


class StoryGenerator:
    """Generate monthly financial narratives from transaction data."""

    def generate(
        self, transactions: list[dict], target_month: Optional[str] = None,
    ) -> dict:
        """Generate a full financial story for a month.

        Returns a dict with: title, month, sections[], summary,
        highlights[], concerns[], tips[], score, tone.
        """
        if not transactions:
            return self._empty_story()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)

        # Pick target month
        if not target_month:
            target_month = str(df["month"].max())

        month_df = df[df["month"] == target_month]
        if month_df.empty:
            target_month = str(df["month"].max())
            month_df = df[df["month"] == target_month]

        # ── Core stats ─────────────────────────────────────────
        debits = month_df[month_df["transaction_type"] == "debit"]
        credits = month_df[month_df["transaction_type"] == "credit"]

        total_spent = float(debits["amount"].sum())
        total_income = float(credits["amount"].sum())
        net = total_income - total_spent
        savings_rate = round(net / total_income * 100, 1) if total_income > 0 else 0
        txn_count = len(month_df)

        # ── Previous month ────────────────────────────────────
        prev = self._get_previous_month(df, target_month)

        # ── Health score & tone ────────────────────────────────
        score = self._calculate_health_score(savings_rate, debits, prev)
        tone = self._get_tone(score)
        month_label = _month_label(target_month)

        # ── Build story sections ───────────────────────────────
        sections = []

        # §1 Summary
        sections.append(self._section_summary(
            tone, month_label, total_income, total_spent, net,
            savings_rate, txn_count, prev,
        ))

        # §2 Spending Breakdown
        sections.append(self._section_spending_breakdown(debits, total_spent))

        # §3 Trend (vs previous month)
        if prev:
            sections.append(self._section_trend(
                total_spent, total_income, net, savings_rate, prev, month_label,
            ))

        # §4 Merchant Spotlight
        sections.append(self._section_merchants(debits))

        # §5 Behavioral Observations
        sections.append(self._section_behavior(debits, month_df))

        # Remove empty sections
        sections = [s for s in sections if s.get("content")]

        # ── Highlights / Concerns / Tips ───────────────────────
        highlights = self._build_highlights(
            debits, total_spent, total_income, net, savings_rate, prev,
        )
        concerns = self._build_concerns(
            debits, total_spent, total_income, savings_rate, prev,
        )
        tips = self._build_tips(debits, savings_rate, total_spent, prev)

        # ── Title ──────────────────────────────────────────────
        random.seed(hash(target_month))
        title = random.choice(_TITLES[tone]).format(month=month_label)

        # ── Full summary paragraph ─────────────────────────────
        summary = sections[0]["content"] if sections else ""

        return {
            "title": title,
            "month": target_month,
            "month_label": month_label,
            "summary": summary,
            "sections": sections,
            "highlights": highlights,
            "concerns": concerns,
            "tips": tips,
            "score": round(score, 1),
            "tone": tone,
            "stats": {
                "total_income": round(total_income, 2),
                "total_spent": round(total_spent, 2),
                "net_savings": round(net, 2),
                "savings_rate": savings_rate,
                "transaction_count": txn_count,
            },
        }

    # ────────────────────────────────────────────────────────────────
    # Section builders
    # ────────────────────────────────────────────────────────────────

    def _section_summary(
        self, tone, month_label, income, spent, net, rate, count, prev,
    ) -> dict:
        random.seed(hash(month_label))
        opener = random.choice(_SUMMARY_OPENERS[tone]).format(
            income=f"{income:,.0f}", spent=f"{spent:,.0f}", txn_count=count,
        )

        if net > 0:
            savings_line = (
                f"You saved ₹{net:,.0f} — a {rate:.1f}% savings rate. "
            )
            if rate > 30:
                savings_line += "That's well above the recommended 20% target. 🎯"
            elif rate > 20:
                savings_line += "You're beating the 20% benchmark — well done."
            else:
                savings_line += "Aim to push this above 20% next month."
        else:
            savings_line = (
                f"Unfortunately, expenses exceeded income by ₹{abs(net):,.0f}. "
                "This means you dipped into savings or accumulated debt."
            )

        trend_line = ""
        if prev:
            spend_change = spent - prev["spent"]
            if spend_change > 0:
                trend_line = (
                    f" Compared to last month, spending increased by "
                    f"₹{spend_change:,.0f} ({abs(spend_change)/prev['spent']*100:.1f}%)."
                )
            elif spend_change < 0:
                trend_line = (
                    f" Great news — spending dropped by "
                    f"₹{abs(spend_change):,.0f} ({abs(spend_change)/prev['spent']*100:.1f}%) from last month."
                )
            else:
                trend_line = " Spending was virtually identical to last month."

        return {
            "heading": "Monthly Overview",
            "icon": "📊",
            "content": f"{opener} {savings_line}{trend_line}",
        }

    def _section_spending_breakdown(self, debits: pd.DataFrame, total: float) -> dict:
        if debits.empty or "category" not in debits.columns:
            return {"heading": "Spending Breakdown", "icon": "📦", "content": ""}

        cats = debits.groupby("category")["amount"].sum().sort_values(ascending=False)
        if cats.empty:
            return {"heading": "Spending Breakdown", "icon": "📦", "content": ""}

        lines = []

        # Top category narrative
        top_cat = str(cats.index[0])
        top_amt = float(cats.iloc[0])
        top_pct = round(top_amt / total * 100, 1)
        top_icon = CATEGORY_ICONS.get(top_cat, "💰")

        lines.append(
            f"Your biggest spending area was {top_icon} **{top_cat}** "
            f"at ₹{top_amt:,.0f} ({top_pct}% of total)."
        )

        if top_pct > 40:
            lines.append(
                f"That's a heavy concentration — consider if all {top_cat} "
                "spending was necessary."
            )

        # 2nd and 3rd categories
        if len(cats) >= 2:
            second = str(cats.index[1])
            s_amt = float(cats.iloc[1])
            s_icon = CATEGORY_ICONS.get(second, "💰")
            lines.append(
                f"Next up was {s_icon} **{second}** (₹{s_amt:,.0f})"
            )
            if len(cats) >= 3:
                third = str(cats.index[2])
                t_amt = float(cats.iloc[2])
                t_icon = CATEGORY_ICONS.get(third, "💰")
                lines[-1] += f", followed by {t_icon} **{third}** (₹{t_amt:,.0f})."
            else:
                lines[-1] += "."

        # Remaining
        if len(cats) > 3:
            remaining = float(cats.iloc[3:].sum())
            lines.append(
                f"The remaining {len(cats) - 3} categories accounted for ₹{remaining:,.0f}."
            )

        return {
            "heading": "Where Your Money Went",
            "icon": "📦",
            "content": " ".join(lines),
        }

    def _section_trend(
        self, spent, income, net, rate, prev, month_label,
    ) -> dict:
        lines = []
        spend_change = spent - prev["spent"]
        spend_pct = abs(spend_change) / prev["spent"] * 100 if prev["spent"] > 0 else 0

        if spend_change > 0:
            if spend_pct > 20:
                lines.append(
                    f"⚠️ Spending surged by {spend_pct:.1f}% compared to last month — "
                    f"that's an extra ₹{spend_change:,.0f}."
                )
            elif spend_pct > 5:
                lines.append(
                    f"Spending crept up by {spend_pct:.1f}% (₹{spend_change:,.0f}) "
                    "from last month."
                )
            else:
                lines.append(
                    f"Spending was essentially flat, up just {spend_pct:.1f}%."
                )
        else:
            if spend_pct > 15:
                lines.append(
                    f"🎉 Impressive! You cut spending by {spend_pct:.1f}% — "
                    f"saving ₹{abs(spend_change):,.0f} vs last month."
                )
            elif spend_pct > 5:
                lines.append(
                    f"You trimmed spending by {spend_pct:.1f}% (₹{abs(spend_change):,.0f}). "
                    "Steady progress."
                )
            else:
                lines.append(
                    f"Spending was nearly unchanged, down just {spend_pct:.1f}%."
                )

        # Income comparison
        if prev.get("income", 0) > 0:
            inc_change = income - prev["income"]
            if inc_change > 0:
                lines.append(
                    f"Income grew by ₹{inc_change:,.0f} — a positive tailwind."
                )
            elif inc_change < 0:
                lines.append(
                    f"Income dipped by ₹{abs(inc_change):,.0f} — worth monitoring."
                )

        # Savings rate comparison
        prev_rate = (
            (prev["income"] - prev["spent"]) / prev["income"] * 100
            if prev.get("income", 0) > 0 else 0
        )
        rate_change = rate - prev_rate
        if abs(rate_change) > 2:
            direction = "improved" if rate_change > 0 else "slipped"
            lines.append(
                f"Your savings rate {direction} from {prev_rate:.1f}% to {rate:.1f}%."
            )

        return {
            "heading": "Month-over-Month Trend",
            "icon": "📈",
            "content": " ".join(lines),
        }

    def _section_merchants(self, debits: pd.DataFrame) -> dict:
        if debits.empty or "merchant_clean" not in debits.columns:
            return {"heading": "Merchant Spotlight", "icon": "🏪", "content": ""}

        merch = debits.groupby("merchant_clean").agg(
            total=("amount", "sum"),
            count=("amount", "count"),
        ).sort_values("total", ascending=False)

        if merch.empty:
            return {"heading": "Merchant Spotlight", "icon": "🏪", "content": ""}

        lines = []
        top = merch.iloc[0]
        top_name = str(merch.index[0])
        lines.append(
            f"Your top merchant was **{top_name}** — you transacted "
            f"{int(top['count'])} times for a total of ₹{float(top['total']):,.0f}."
        )

        if int(top["count"]) > 15:
            lines.append(f"That's quite frequent — is every {top_name} transaction essential?")

        # High-frequency merchants
        frequent = merch[merch["count"] >= 8]
        if len(frequent) > 1:
            names = [str(n) for n in frequent.index[1:4]]
            lines.append(
                f"Other frequent merchant{'s' if len(names) > 1 else ''}: "
                f"{', '.join(names)}."
            )

        return {
            "heading": "Merchant Spotlight",
            "icon": "🏪",
            "content": " ".join(lines),
        }

    def _section_behavior(self, debits: pd.DataFrame, all_txns: pd.DataFrame) -> dict:
        if debits.empty:
            return {"heading": "Behavioral Patterns", "icon": "🧠", "content": ""}

        lines = []

        # Weekend vs weekday
        debits_copy = debits.copy()
        debits_copy["dow"] = debits_copy["date"].dt.dayofweek
        weekend = debits_copy[debits_copy["dow"].isin([5, 6])]
        weekday = debits_copy[~debits_copy["dow"].isin([5, 6])]

        if not weekend.empty and not weekday.empty:
            we_avg = float(weekend["amount"].mean())
            wd_avg = float(weekday["amount"].mean())
            if we_avg > wd_avg * 1.3:
                pct = round((we_avg - wd_avg) / wd_avg * 100)
                lines.append(
                    f"You spent {pct}% more per transaction on weekends "
                    f"(avg ₹{we_avg:,.0f}) vs weekdays (avg ₹{wd_avg:,.0f})."
                )

        # Late-night
        if "time_hour" in debits.columns:
            timed = debits[debits["time_hour"].notna()]
            if not timed.empty:
                late = timed[
                    timed["time_hour"].astype(float).between(22, 23)
                    | timed["time_hour"].astype(float).between(0, 4)
                ]
                if len(late) >= 3:
                    late_total = float(late["amount"].sum())
                    lines.append(
                        f"You made {len(late)} late-night transactions "
                        f"(10pm–4am) totaling ₹{late_total:,.0f}. "
                        "Late-night purchases are often impulsive."
                    )

        # Micro-spending
        micro = debits[debits["amount"] <= 300]
        if len(micro) >= 5:
            micro_total = float(micro["amount"].sum())
            lines.append(
                f"You had {len(micro)} small transactions (≤₹300) totaling "
                f"₹{micro_total:,.0f}. These 'invisible' expenses add up fast."
            )

        if not lines:
            return {"heading": "Behavioral Patterns", "icon": "🧠", "content": ""}

        return {
            "heading": "Behavioral Patterns",
            "icon": "🧠",
            "content": " ".join(lines),
        }

    # ────────────────────────────────────────────────────────────────
    # Highlights / Concerns / Tips
    # ────────────────────────────────────────────────────────────────

    def _build_highlights(self, debits, spent, income, net, rate, prev) -> list[str]:
        h = []
        if rate > 30:
            h.append(f"💪 Outstanding savings rate of {rate:.1f}% — top-tier discipline")
        elif rate > 20:
            h.append(f"💪 Strong savings rate of {rate:.1f}%")
        if net > 0:
            h.append(f"✅ Positive cash flow — you saved ₹{net:,.0f}")
        if prev and spent < prev["spent"]:
            pct = round((prev["spent"] - spent) / prev["spent"] * 100, 1)
            h.append(f"📉 Spending dropped {pct}% from last month")
        if prev and rate > 0:
            prev_rate = (prev["income"] - prev["spent"]) / prev["income"] * 100 if prev.get("income", 0) > 0 else 0
            if rate > prev_rate + 3:
                h.append(f"📈 Savings rate improved from {prev_rate:.1f}% → {rate:.1f}%")

        if not debits.empty and "category" in debits.columns:
            cats = debits.groupby("category")["amount"].sum()
            top = str(cats.idxmax())
            icon = CATEGORY_ICONS.get(top, "💰")
            h.append(f"{icon} Top category: {top} (₹{float(cats.max()):,.0f})")

        return h[:6]

    def _build_concerns(self, debits, spent, income, rate, prev) -> list[str]:
        c = []
        if rate < 0:
            c.append("❌ You spent more than you earned — you're running a deficit")
        elif rate < 10 and income > 0:
            c.append(f"⚠️ Savings rate of {rate:.1f}% is dangerously low — target 20%+")
        if prev and spent > prev["spent"] * 1.2:
            pct = round((spent - prev["spent"]) / prev["spent"] * 100, 1)
            c.append(f"📈 Spending jumped {pct}% vs last month")
        if not debits.empty and "category" in debits.columns:
            cats = debits.groupby("category")["amount"].sum()
            total = float(cats.sum())
            top_pct = float(cats.max()) / total * 100 if total > 0 else 0
            if top_pct > 50:
                c.append(f"⚠️ Over {top_pct:.0f}% of spending is in one category")
        if not debits.empty:
            daily = debits.groupby(debits["date"].dt.date).size()
            if int(daily.max()) > 8:
                c.append(f"🔴 {int(daily.max())} transactions in a single day — impulse risk")
        return c[:5]

    def _build_tips(self, debits, rate, spent, prev) -> list[str]:
        t = []
        if rate < 20:
            t.append("💡 Adopt the 50/30/20 rule: 50% needs, 30% wants, 20% savings")
        if not debits.empty and "category" in debits.columns:
            food = float(debits[debits["category"] == "Food & Dining"]["amount"].sum())
            if food > spent * 0.25:
                t.append("🍳 Food is 25%+ of spending — cooking 5 more meals/month saves ~₹3,000")
            shop = float(debits[debits["category"] == "Shopping"]["amount"].sum())
            if shop > spent * 0.20:
                t.append("🛒 Try a 48-hour rule before any shopping purchase over ₹500")
            subs = float(debits[debits["category"].isin(["Entertainment", "Subscriptions"])]["amount"].sum())
            if subs > 1000:
                t.append("📱 Audit your subscriptions — most people overpay by ₹500+/month")
        if prev and spent > prev["spent"]:
            t.append(f"🎯 Set next month's target at ₹{spent * 0.9:,.0f} (10% below this month)")
        micro = debits[debits["amount"] <= 200] if not debits.empty else pd.DataFrame()
        if len(micro) > 10:
            t.append("☕ Track micro-spending: those ₹50-200 transactions add up to thousands")
        if rate > 20:
            t.append("🏦 Consider auto-transferring your savings to a high-yield account")
        return t[:6]

    # ────────────────────────────────────────────────────────────────
    # Health score
    # ────────────────────────────────────────────────────────────────

    def _calculate_health_score(self, rate, debits, prev) -> float:
        score = 50.0

        # Savings rate (0-30 pts)
        if rate > 30:
            score += 30
        elif rate > 20:
            score += 22
        elif rate > 10:
            score += 12
        elif rate > 0:
            score += 5
        else:
            score -= 20

        # Spending trend (0-20 pts)
        if prev and prev["spent"] > 0:
            change_pct = (float(debits["amount"].sum()) - prev["spent"]) / prev["spent"] * 100
            if change_pct < -10:
                score += 20
            elif change_pct < 0:
                score += 10
            elif change_pct > 20:
                score -= 15
            elif change_pct > 10:
                score -= 5

        # Category diversity (0-10 pts)
        if not debits.empty and "category" in debits.columns:
            n = debits["category"].nunique()
            if n >= 5:
                score += 10
            elif n >= 3:
                score += 5

        # No single category > 60% (-5 pts)
        if not debits.empty and "category" in debits.columns:
            total = float(debits["amount"].sum())
            if total > 0:
                top_pct = float(debits.groupby("category")["amount"].sum().max()) / total * 100
                if top_pct > 60:
                    score -= 5

        return max(0, min(100, score))

    # ────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_tone(score: float) -> str:
        if score >= 85:
            return "celebratory"
        if score >= 60:
            return "encouraging"
        if score >= 40:
            return "neutral"
        return "concerned"

    def _get_previous_month(self, df: pd.DataFrame, target: str) -> Optional[dict]:
        months = sorted(df["month"].unique())
        months_list = [str(m) for m in months]
        if target not in months_list:
            return None
        idx = months_list.index(target)
        if idx == 0:
            return None

        prev_month = months_list[idx - 1]
        prev_df = df[df["month"] == prev_month]
        prev_debits = prev_df[prev_df["transaction_type"] == "debit"]
        prev_credits = prev_df[prev_df["transaction_type"] == "credit"]

        return {
            "month": prev_month,
            "spent": float(prev_debits["amount"].sum()),
            "income": float(prev_credits["amount"].sum()),
        }

    @staticmethod
    def _empty_story() -> dict:
        return {
            "title": "📋 No Data Available",
            "month": "N/A",
            "month_label": "N/A",
            "summary": "Upload a bank statement to get your monthly financial story.",
            "sections": [],
            "highlights": [],
            "concerns": [],
            "tips": ["💡 Start by uploading a CSV bank statement"],
            "score": 0,
            "tone": "neutral",
            "stats": {},
        }
