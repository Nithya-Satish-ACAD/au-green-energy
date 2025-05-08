# utils/csv_loader.py
import pandas as pd

def load_csv_summary(filepath: str) -> str:
    # df = pd.read_csv(filepath, parse_dates=["timestamp"])
    df = pd.read_csv(filepath)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Extract useful stats
    # daily = df.groupby(df["timestamp"].dt.date).sum()
    daily = df.groupby(df["timestamp"].dt.date).agg({df.columns[1]: 'sum'})
    peak_day = daily.idxmax().values[0]
    peak_value = daily.max().values[0]
    avg_per_hour = df.iloc[:, 1].mean()

    summary = (
        f"Data loaded from {filepath}.\n"
        f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}\n"
        f"Total records: {len(df)}\n"
        f"Average per hour: {avg_per_hour:.2f} kWh\n"
        f"Peak day: {peak_day} with {peak_value:.2f} kWh"
    )

    return summary
