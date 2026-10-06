# Power BI Setup

Zuerst:

```bash
python 01_python_data_cleaning.py
```

Danach in Power BI Desktop nur Dateien aus `data/processed/` laden, nicht die Original-Excels.

Stand Juli 2026 zum Gegenprüfen: Sell-in 26.534 | Sell-out 17.176 | Forecast 9.358

## 1. Dateien laden

**Daten abrufen → Text/CSV**

| Datei | Wofür |
|---|---|
| `fact_fleet_snapshot.csv` | Lifetime je Kunde und Typ (Ord / Del / Opr) |
| `fact_orders_deliveries.csv` | Orders und Deliveries mit Datum, 2021–2026 |
| `dim_date.csv` | Kalender |
| `dim_family.csv` | Flugzeugtyp → Familie |
| `dim_customer.csv` | Kunde, Land, Region |
| `dim_region.csv` | Region-Codes |

Nicht laden: `file_inventory.csv`, `data_quality_report.json`.

## 2. Beziehungen (Sternschema)

```
dim_date[date_key]          1—*  fact_orders_deliveries[date_key]
dim_family[aircraft_type]   1—*  fact_orders_deliveries[aircraft_type]
dim_family[aircraft_type]   1—*  fact_fleet_snapshot[aircraft_type]
dim_customer[customer]      1—*  fact_orders_deliveries[customer]
dim_customer[customer]      1—*  fact_fleet_snapshot[customer]
dim_region[region_code]     1—*  dim_customer[region_code]
```

Kreuzfilterung: einzeln.

Lifetime-KPIs kommen aus dem Snapshot. Die nicht nach Jahr filtern, sonst werden Sell-in / Sell-out leer.

## 3. DAX

Neue Maßzahl, am besten an `fact_fleet_snapshot`:

```dax
Sell-in =
CALCULATE(
    SUM(fact_fleet_snapshot[units]),
    fact_fleet_snapshot[metric] = "Ord"
)

Sell-out =
CALCULATE(
    SUM(fact_fleet_snapshot[units]),
    fact_fleet_snapshot[metric] = "Del"
)

Forecast =
[Sell-in] - [Sell-out]

Event Units =
SUM(fact_orders_deliveries[units])
```

## 4. Bericht (eine Seite)

So wie im Screenshot:

- drei Kacheln: Sell-in, Sell-out, Forecast
- Tabelle: Familie mit Sell-in / Sell-out / Forecast
- Balken: Forecast nach Familie
- Linie: Orders vs Deliveries nach Jahr (`event_type`)
- Karte: Sell-out nach Land

Slicer: Family, Region. Jahr nur an die Zeitreihe, nicht an die Lifetime-Kacheln.
