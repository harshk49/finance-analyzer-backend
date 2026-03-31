"""Forecast Engine — predict next month spending using simple time series.

Uses exponential smoothing for robustness (no Prophet dependency required
for basic predictions).
"""
import numpy as np
import pandas as pd
from typing import Optional

from server.schemas.analytics import ForecastData


class ForecastEngine:
    """Predict future spending based on historical patterns."""

    def forecast(self, transactions: list[dict], months_ahead: int = 3) -> list[ForecastData]:
        """Forecast next N months of spending."""
        if not transactions:
            return []

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        debits = df[df["transaction_type"] == "debit"]

        if debits.empty:
            return []

        # Monthly spending series
        monthly = debits.groupby(df["date"].dt.to_period("M"))["amount"].sum()
        
        if len(monthly) < 3:
            # Not enough data — use simple average
            avg = monthly.mean()
            std = monthly.std() if len(monthly) > 1 else avg * 0.2
            return self._simple_forecast(monthly, avg, std, months_ahead)

        values = monthly.values.astype(float)

        # Exponential smoothing
        alpha = 0.3  # Smoothing factor
        forecasts = []
        
        # Calculate smoothed values
        smoothed = [values[0]]
        for v in values[1:]:
            smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])

        # Trend component
        if len(smoothed) >= 2:
            trend = smoothed[-1] - smoothed[-2]
        else:
            trend = 0

        # Forecast
        last_period = monthly.index[-1]
        residuals = values - np.array(smoothed)
        std_residual = np.std(residuals) if len(residuals) > 1 else values.std()

        for i in range(1, months_ahead + 1):
            predicted = smoothed[-1] + trend * i
            predicted = max(0, predicted)  # Spending can't be negative

            # Confidence intervals widen over time
            uncertainty = std_residual * np.sqrt(i)
            lower = max(0, predicted - 1.96 * uncertainty)
            upper = predicted + 1.96 * uncertainty

            # Calculate future month period
            future_month = last_period + i
            confidence = max(0.3, min(0.95, 1 - 0.1 * i))

            forecasts.append(ForecastData(
                month=str(future_month),
                predicted_spending=round(predicted, 2),
                lower_bound=round(lower, 2),
                upper_bound=round(upper, 2),
                confidence=round(confidence, 2),
            ))

        return forecasts

    def _simple_forecast(self, monthly, avg, std, months_ahead) -> list[ForecastData]:
        """Simple average-based forecast when data is limited."""
        last_period = monthly.index[-1]
        forecasts = []

        for i in range(1, months_ahead + 1):
            future_month = last_period + i
            forecasts.append(ForecastData(
                month=str(future_month),
                predicted_spending=round(avg, 2),
                lower_bound=round(max(0, avg - 1.96 * std), 2),
                upper_bound=round(avg + 1.96 * std, 2),
                confidence=round(max(0.3, 0.6 - 0.1 * i), 2),
            ))

        return forecasts
