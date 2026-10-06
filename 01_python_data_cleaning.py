"""
Airbus Orders & Deliveries.

Monats-Excels sind YTD-Snapshots. Deshalb eine Datei pro Jahr
(Dezember, 2026 = Juli), nicht alle 67 Dateien hintereinander.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

FAMILY_MAP = {
    "A220-100": "A220",
    "A220-300": "A220",
    "A220": "A220",
    "A318": "A320 Family",
    "A319ceo": "A320 Family",
    "A319neo": "A320 Family",
    "A320ceo": "A320 Family",
    "A320neo": "A320 Family",
    "A321ceo": "A320 Family",
    "A321neo": "A320 Family",
    "A320Family": "A320 Family",
    "A320 Family": "A320 Family",
    "A300": "A300/A310",
    "A310": "A300/A310",
    "A300/A310": "A300/A310",
    "A330-200": "A330",
    "A330-200F": "A330",
    "A330-300": "A330",
    "A330-800": "A330",
    "A330-900": "A330",
    "A330": "A330",
    "A340-200/300": "A340",
    "A340-500/600": "A340",
    "A340": "A340",
    "A350F": "A350",
    "A350-900": "A350",
    "A350-1000": "A350",
    "A350": "A350",
    "A380": "A380",
}

REGION_MAP = {
    "A": "Asia-Pacific",
    "F": "Africa",
    "E": "Europe and CIS",
    "L": "Latin America & Caribbean",
    "M": "Middle East",
    "N": "North America",
}

SKIP_CUSTOMERS = {
    "TOTAL", "TOTAL GROSS ORDERS", "TOTAL CANCELLATIONS", "TOTAL NET ORDERS",
    "GRAND TOTAL", "TOTAL TO DATE",
}


def parse_filename(path: Path) -> tuple[int | None, int | None]:
    name = path.stem.lower().replace("_", "-")
    year = None
    month = None
    m_year = re.search(r"(20[2-3][0-9])", name)
    if m_year:
        year = int(m_year.group(1))
    for label, num in MONTHS.items():
        if label in name:
            month = num
            break
    if month is None:
        m_oad = re.search(r"oad[_-]?(20[2-3][0-9])[_-]?(\d{1,2})", name)
        if m_oad:
            year = int(m_oad.group(1))
            month = int(m_oad.group(2))
    return year, month


def list_monthly_files() -> pd.DataFrame:
    rows = []
    for year in RAW_YEARS:
        folder = ROOT / str(year)
        if not folder.exists():
            continue
        for path in folder.glob("*.xlsx"):
            y, m = parse_filename(path)
            rows.append({
                "year": y or year,
                "month": m,
                "path": path,
                "name": path.name,
            })
    return pd.DataFrame(rows).sort_values(["year", "month"], na_position="last")


def year_end_files(inventory: pd.DataFrame) -> pd.DataFrame:
    """Eine Datei pro Kalenderjahr: Dezember, sonst der späteste Monat (2026 = Juli)."""
    chosen = []
    for year, group in inventory.dropna(subset=["month"]).groupby("year"):
        if year < 2026:
            dec = group[group["month"] == 12]
            chosen.append(dec.iloc[-1] if not dec.empty else group.iloc[-1])
        else:
            chosen.append(group.sort_values("month").iloc[-1])
    return pd.DataFrame(chosen)


def find_sheet(xl: pd.ExcelFile, *candidates: str) -> str | None:
    lower = {s.lower(): s for s in xl.sheet_names}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    for key, original in lower.items():
        if any(c.lower() in key for c in candidates):
            return original
    return None


def find_header_row(raw: pd.DataFrame, must_contain: str = "CUSTOMER") -> int:
    for i in range(min(25, len(raw))):
        values = [str(v).strip().upper() for v in raw.iloc[i].tolist() if pd.notna(v)]
        if must_contain.upper() in values:
            return i
    raise ValueError(f"Header '{must_contain}' not found")


def is_aircraft_col(name: str) -> bool:
    if not name or name in {"CUSTOMER", "REGION", "DATE OF ORDER", "DATE OF DELIVERY", "TOTAL", "NAN"}:
        return False
    return bool(re.match(r"^A\d", name.replace(" ", "")))


def melt_event_sheet(path: Path, sheet_kind: str) -> pd.DataFrame:
    xl = pd.ExcelFile(path)
    sheet = find_sheet(xl, sheet_kind)
    if sheet is None:
        return pd.DataFrame()

    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_row = find_header_row(raw)
    headers = [str(c).strip() if pd.notna(c) else f"col_{i}" for i, c in enumerate(raw.iloc[header_row])]
    df = raw.iloc[header_row + 1:].copy()
    df.columns = headers
    df = df.rename(columns=lambda c: str(c).strip())

    date_col = "Date of order" if sheet_kind.lower() == "orders" else "Date of delivery"
    if date_col not in df.columns:
        for col in df.columns:
            if "date" in str(col).lower():
                date_col = col
                break

    aircraft_cols = [c for c in df.columns if is_aircraft_col(str(c).upper())]
    keep = ["CUSTOMER"]
    if "Region" in df.columns:
        keep.append("Region")
    keep.append(date_col)
    keep.extend(aircraft_cols)
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()
    df = df[df["CUSTOMER"].notna()]
    df["CUSTOMER"] = df["CUSTOMER"].astype(str).str.strip()
    df = df[~df["CUSTOMER"].str.upper().isin(SKIP_CUSTOMERS)]
    df = df[~df["CUSTOMER"].str.upper().str.startswith("TOTAL")]

    long = df.melt(
        id_vars=[c for c in df.columns if c not in aircraft_cols],
        value_vars=aircraft_cols,
        var_name="aircraft_type",
        value_name="units",
    )
    long["units"] = pd.to_numeric(long["units"], errors="coerce").fillna(0)
    long = long[long["units"] != 0].copy()
    long["event_date"] = pd.to_datetime(long[date_col], errors="coerce")
    long = long.dropna(subset=["event_date"])
    long["event_type"] = "order" if sheet_kind.lower() == "orders" else "delivery"
    long["family"] = long["aircraft_type"].map(FAMILY_MAP).fillna(long["aircraft_type"])
    if "Region" in long.columns:
        long["region_code"] = long["Region"].astype(str).str.strip().str.upper()
        long["region"] = long["region_code"].map(REGION_MAP).fillna("Unknown")
    else:
        long["region_code"] = pd.NA
        long["region"] = "Unknown"
    long["customer"] = long["CUSTOMER"].str.upper()
    long["year"] = long["event_date"].dt.year
    long["month"] = long["event_date"].dt.month
    long["source_file"] = path.name
    return long[["event_type", "event_date", "year", "month", "customer", "region_code",
                 "region", "aircraft_type", "family", "units", "source_file"]]


def parse_worldwide(path: Path) -> pd.DataFrame:
    """Lifetime snapshot: Orders / Deliveries / In Operation je Kunde und Typ."""
    xl = pd.ExcelFile(path)
    sheet = find_sheet(xl, "Worldwide")
    if sheet is None:
        return pd.DataFrame()

    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    type_row = None
    metric_row = None
    for i in range(min(25, len(raw))):
        vals = [str(v).strip() for v in raw.iloc[i].tolist() if pd.notna(v)]
        if any(v in FAMILY_MAP or re.match(r"^A\d", v) for v in vals) and "TOTAL" in [v.upper() for v in vals]:
            type_row = i
        if {"Ord", "Del", "Opr"} <= set(vals) or vals.count("Ord") >= 3:
            metric_row = i
            break
    if type_row is None or metric_row is None:
        raise ValueError(f"Worldwide header not found in {path.name}")

    types = []
    current = None
    for col in range(raw.shape[1]):
        t = raw.iloc[type_row, col]
        m = raw.iloc[metric_row, col]
        if pd.notna(t) and str(t).strip() not in {"", "CUSTOMER", "Region"}:
            current = str(t).strip()
        types.append((current, str(m).strip() if pd.notna(m) else ""))

    header_vals = [str(v).strip().upper() for v in raw.iloc[metric_row].tolist() if pd.notna(v)]
    customer_row = metric_row if "CUSTOMER" in header_vals else metric_row - 1
    df = raw.iloc[metric_row + 1:].copy()

    customer_col = 0
    country_col = None
    region_col = None
    first = df.iloc[0]
    if pd.notna(first.iloc[0]) and str(first.iloc[0]).strip().isdigit():
        customer_col = 1
        country_col = 2
        region_col = 3
    else:
        for col, val in enumerate(first):
            if pd.notna(val) and str(val).strip().upper() in REGION_MAP:
                region_col = col
                country_col = col - 1 if col >= 1 else None
                break
        if country_col is None:
            country_col = 4 if df.shape[1] > 4 else 1
            region_col = 6 if df.shape[1] > 6 else 2

    records = []
    for _, row in df.iterrows():
        customer = row.iloc[customer_col]
        if pd.isna(customer):
            continue
        customer = str(customer).strip()
        if customer.upper() in SKIP_CUSTOMERS or customer.upper().startswith("TOTAL"):
            continue
        country = str(row.iloc[country_col]).strip() if country_col is not None and pd.notna(row.iloc[country_col]) else ""
        region_code = str(row.iloc[region_col]).strip().upper() if region_col is not None and pd.notna(row.iloc[region_col]) else ""
        for col, (aircraft, metric) in enumerate(types):
            if aircraft in {None, "CUSTOMER", "Region"} or metric not in {"Ord", "Del", "Opr"}:
                continue
            if aircraft.upper() == "TOTAL":
                continue
            val = pd.to_numeric(row.iloc[col], errors="coerce")
            if pd.isna(val) or val == 0:
                continue
            records.append({
                "customer": customer.upper(),
                "country": country.upper(),
                "region_code": region_code,
                "region": REGION_MAP.get(region_code, "Unknown"),
                "aircraft_type": aircraft,
                "family": FAMILY_MAP.get(aircraft, aircraft),
                "metric": metric,
                "units": int(val),
                "source_file": path.name,
            })
    return pd.DataFrame(records)


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if not isinstance(obj, (list, dict, str, bool)) and pd.isna(obj):
        return None
    if hasattr(obj, "item") and not isinstance(obj, (bytes, str)):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return obj


def append_new_month(new_file: Path, history_csv: Path) -> pd.DataFrame:
    """Neue Monatsdatei an die Historie haengen, ohne YTD-Duplikate."""
    y, m = parse_filename(new_file)
    deliveries = melt_event_sheet(new_file, "Deliveries")
    orders = melt_event_sheet(new_file, "Orders")
    incoming = pd.concat([deliveries, orders], ignore_index=True)
    incoming["snapshot_year"] = y
    incoming["snapshot_month"] = m

    if history_csv.exists():
        history = pd.read_csv(history_csv, parse_dates=["event_date"])
        key = ["event_type", "event_date", "customer", "aircraft_type", "units"]
        combined = pd.concat([history, incoming], ignore_index=True)
        combined = combined.drop_duplicates(subset=key, keep="last")
    else:
        combined = incoming
    combined.to_csv(history_csv, index=False)
    return combined


def kpi_summary(events: pd.DataFrame, fleet: pd.DataFrame) -> dict:
    orders = events[events["event_type"] == "order"]
    deliveries = events[events["event_type"] == "delivery"]

    latest_year = int(events["year"].max())
    prev_year = latest_year - 1
    del_latest = deliveries[deliveries["year"] == latest_year]["units"].sum()
    del_prev = deliveries[deliveries["year"] == prev_year]["units"].sum()

    family_perf = deliveries.groupby("family", as_index=False)["units"].sum().rename(columns={"units": "delivered"})
    family_ord = orders.groupby("family", as_index=False)["units"].sum().rename(columns={"units": "ordered"})
    family = family_ord.merge(family_perf, on="family", how="outer").fillna(0)
    family["delivery_rate"] = family["delivered"] / family["ordered"].replace(0, pd.NA)
    family["delivery_rate"] = pd.to_numeric(family["delivery_rate"], errors="coerce")

    snap = fleet.groupby(["family", "metric"], as_index=False)["units"].sum()
    snap_wide = snap.pivot_table(index="family", columns="metric", values="units", aggfunc="sum").fillna(0)
    snap_wide["backlog"] = snap_wide.get("Ord", 0) - snap_wide.get("Del", 0)
    snap_wide["fulfillment_rate"] = snap_wide.get("Del", 0) / snap_wide.get("Ord", 0).replace(0, pd.NA)
    snap_wide["fulfillment_rate"] = pd.to_numeric(snap_wide["fulfillment_rate"], errors="coerce")

    top_customers = (
        fleet[fleet["metric"] == "Ord"]
        .groupby("customer", as_index=False)["units"].sum()
        .sort_values("units", ascending=False)
        .head(10)
    )

    region_del = deliveries.groupby("region", as_index=False)["units"].sum().sort_values("units", ascending=False)

    yoy = []
    for year in sorted(deliveries["year"].unique()):
        yoy.append({
            "year": int(year),
            "orders": int(orders[orders["year"] == year]["units"].sum()),
            "deliveries": int(deliveries[deliveries["year"] == year]["units"].sum()),
        })

    return {
        "coverage": {
            "event_rows": int(len(events)),
            "order_units_ytd_files": int(orders["units"].sum()),
            "delivery_units_ytd_files": int(deliveries["units"].sum()),
            "fleet_customers": int(fleet["customer"].nunique()),
            "latest_snapshot": fleet["source_file"].iloc[0] if len(fleet) else None,
        },
        "kpis": {
            "sell_in": int(fleet[fleet["metric"] == "Ord"]["units"].sum()),
            "sell_out": int(fleet[fleet["metric"] == "Del"]["units"].sum()),
            "in_operation": int(fleet[fleet["metric"] == "Opr"]["units"].sum()),
            "forecast": int(
                fleet[fleet["metric"] == "Ord"]["units"].sum()
                - fleet[fleet["metric"] == "Del"]["units"].sum()
            ),
        },
        "by_family": snap_wide.reset_index().to_dict(orient="records"),
        "yoy_delivery": {
            "latest_year": latest_year,
            "latest_deliveries": int(del_latest),
            "previous_year": prev_year,
            "previous_deliveries": int(del_prev),
            "yoy_pct": None if del_prev == 0 else round((del_latest / del_prev - 1) * 100, 1),
        },
        "top_customers": top_customers.to_dict(orient="records"),
        "deliveries_by_region": region_del.to_dict(orient="records"),
        "trend": yoy,
        "family_from_events": family.sort_values("ordered", ascending=False).to_dict(orient="records"),
    }


def main() -> None:
    print("=" * 64)
    print("AIRBUS ORDERS & DELIVERIES - DATA CLEANING")
    print("=" * 64)

    inventory = list_monthly_files()
    print(f"\n1. Dateien gefunden: {len(inventory)} Excel in Jahresordnern 2021-2026")
    missing_months = inventory[inventory["month"].isna()]
    if len(missing_months):
        print("   Dateien ohne klaren Monat:")
        for name in missing_months["name"]:
            print(f"   - {name}")

    selected = year_end_files(inventory)
    print("\n2. Genutzte Snapshots (kein YTD-Duplikat):")
    for _, row in selected.iterrows():
        print(f"   {int(row['year'])}-{int(row['month']):02d}  {row['name']}")

    print("\n3. Orders & Deliveries einlesen (wide -> long)...")
    frames = []
    quality = {"files_ok": [], "files_failed": []}
    for _, row in selected.iterrows():
        path = Path(row["path"])
        try:
            orders = melt_event_sheet(path, "Orders")
            deliveries = melt_event_sheet(path, "Deliveries")
            frames.extend([orders, deliveries])
            quality["files_ok"].append({
                "file": path.name,
                "orders": int(orders["units"].sum()) if len(orders) else 0,
                "deliveries": int(deliveries["units"].sum()) if len(deliveries) else 0,
            })
            print(f"   {path.name}: orders={quality['files_ok'][-1]['orders']}, "
                  f"deliveries={quality['files_ok'][-1]['deliveries']}")
        except Exception as exc:
            quality["files_failed"].append({"file": path.name, "error": str(exc)})
            print(f"   FEHLER {path.name}: {exc}")

    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    latest = selected.sort_values(["year", "month"]).iloc[-1]
    print(f"\n4. Worldwide-Snapshot (Lifetime): {latest['name']}")
    fleet = parse_worldwide(Path(latest["path"]))
    print(f"   {len(fleet)} Kennzahl-Zeilen, {fleet['customer'].nunique()} Kunden")

    print("\n5. Star-Schema exportieren...")
    dim_family = pd.DataFrame(
        [{"aircraft_type": k, "family": v} for k, v in FAMILY_MAP.items()]
    ).drop_duplicates()
    dim_region = pd.DataFrame([{"region_code": k, "region": v} for k, v in REGION_MAP.items()])
    dim_customer = (
        fleet[["customer", "country", "region_code", "region"]]
        .drop_duplicates(subset=["customer"])
        .sort_values("customer")
    )
    dim_date = pd.DataFrame({"date": pd.date_range("2021-01-01", "2026-12-31", freq="D")})
    dim_date["date_key"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["year"] = dim_date["date"].dt.year
    dim_date["month"] = dim_date["date"].dt.month
    dim_date["year_month"] = dim_date["date"].dt.strftime("%Y-%m")
    dim_date["month_name"] = dim_date["date"].dt.strftime("%B")

    fact_events = events.copy()
    if len(fact_events):
        fact_events["date_key"] = fact_events["event_date"].dt.strftime("%Y%m%d").astype(int)
        # "7.0" is read as 70 by Power BI with German locale
        fact_events["units"] = fact_events["units"].astype(int)

    fact_fleet = fleet.copy()
    fact_events.to_csv(PROCESSED / "fact_orders_deliveries.csv", index=False)
    fact_fleet.to_csv(PROCESSED / "fact_fleet_snapshot.csv", index=False)
    dim_family.to_csv(PROCESSED / "dim_family.csv", index=False)
    dim_region.to_csv(PROCESSED / "dim_region.csv", index=False)
    dim_customer.to_csv(PROCESSED / "dim_customer.csv", index=False)
    dim_date.to_csv(PROCESSED / "dim_date.csv", index=False)
    inventory.assign(path=inventory["path"].astype(str)).to_csv(PROCESSED / "file_inventory.csv", index=False)

    summary = kpi_summary(events, fleet)
    quality["selected_files"] = selected["name"].tolist()
    quality["note"] = (
        "Nicht alle 67 Monate konkateniert: Orders/Deliveries sind YTD. "
        "December-Dateien enthalten das volle Jahr."
    )
    report = {"quality": quality, "kpis": summary}
    with open(PROCESSED / "data_quality_report.json", "w", encoding="utf-8") as f:
        json.dump(json_safe(report), f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print("KPIs")
    print("=" * 64)
    a = summary["kpis"]
    print(f"  Sell-in:      {a['sell_in']:,}")
    print(f"  Sell-out:     {a['sell_out']:,}")
    print(f"  Forecast:     {a['forecast']:,}")
    print(f"  In operation: {a['in_operation']:,}")

    print("\nNach Familie:")
    for row in summary["by_family"]:
        rate = row.get("fulfillment_rate")
        rate_txt = f"{float(rate):.1%}" if rate is not None and pd.notna(rate) else "n/a"
        print(f"  {row['family']:<14} Ord={int(row.get('Ord', 0)):>6}  "
              f"Del={int(row.get('Del', 0)):>6}  Forecast={int(row.get('backlog', 0)):>6}  Rate={rate_txt}")

    yoy = summary["yoy_delivery"]
    print(f"\n  YoY Deliveries {yoy['previous_year']} -> {yoy['latest_year']}: "
          f"{yoy['previous_deliveries']:,} -> {yoy['latest_deliveries']:,}  ({yoy['yoy_pct']}%)")
    print("  2026 = YTD Juli.")

    print("\nTop Kunden (Sell-in):")
    for i, row in enumerate(summary["top_customers"], 1):
        print(f"  {i:>2}. {row['customer']:<40} {int(row['units']):>6}")

    print("\nExport:")
    print(f"  {PROCESSED / 'fact_orders_deliveries.csv'}")
    print(f"  {PROCESSED / 'fact_fleet_snapshot.csv'}")
    print(f"  {PROCESSED / 'dim_*.csv'}")
    print(f"  {PROCESSED / 'data_quality_report.json'}")
    print("\nNaechster Schritt: Power BI <- data/processed/*.csv")
    print("=" * 64)


if __name__ == "__main__":
    main()
