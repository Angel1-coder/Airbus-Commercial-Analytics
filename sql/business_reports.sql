-- Airbus Orders & Deliveries — Business Reports
-- Quelle: data/processed/fact_orders_deliveries.csv
--         data/processed/fact_fleet_snapshot.csv

-- ============================================
-- REPORT 1: Executive Snapshot
-- ============================================
SELECT
    SUM(CASE WHEN metric = 'Ord' THEN units END) AS lifetime_orders,
    SUM(CASE WHEN metric = 'Del' THEN units END) AS lifetime_deliveries,
    SUM(CASE WHEN metric = 'Opr' THEN units END) AS in_operation,
    SUM(CASE WHEN metric = 'Ord' THEN units END)
      - SUM(CASE WHEN metric = 'Del' THEN units END) AS backlog
FROM fact_fleet_snapshot;

-- Erwartung Juli 2026: 26534 / 17176 / 14511 / 9358

-- ============================================
-- REPORT 2: Delivery Rate je Family
-- ============================================
SELECT
    family,
    SUM(CASE WHEN metric = 'Ord' THEN units END) AS ordered,
    SUM(CASE WHEN metric = 'Del' THEN units END) AS delivered,
    SUM(CASE WHEN metric = 'Ord' THEN units END)
      - SUM(CASE WHEN metric = 'Del' THEN units END) AS backlog,
    ROUND(
        100.0 * SUM(CASE WHEN metric = 'Del' THEN units END)
        / NULLIF(SUM(CASE WHEN metric = 'Ord' THEN units END), 0)
    , 1) AS delivery_rate_pct
FROM fact_fleet_snapshot
GROUP BY family
ORDER BY backlog DESC;

-- ============================================
-- REPORT 3: Top Kunden
-- ============================================
SELECT
    customer,
    country,
    region,
    SUM(CASE WHEN metric = 'Ord' THEN units END) AS lifetime_orders,
    SUM(CASE WHEN metric = 'Del' THEN units END) AS lifetime_deliveries
FROM fact_fleet_snapshot
GROUP BY customer, country, region
ORDER BY lifetime_orders DESC
LIMIT 10;

-- ============================================
-- REPORT 4: YoY Deliveries (Achtung: 2026 = YTD Jul)
-- ============================================
SELECT
    year,
    SUM(CASE WHEN event_type = 'order' THEN units END) AS orders,
    SUM(CASE WHEN event_type = 'delivery' THEN units END) AS deliveries
FROM fact_orders_deliveries
GROUP BY year
ORDER BY year;

-- ============================================
-- REPORT 5: Region
-- ============================================
SELECT
    region,
    SUM(CASE WHEN event_type = 'delivery' THEN units END) AS deliveries_2021_2026
FROM fact_orders_deliveries
GROUP BY region
ORDER BY deliveries_2021_2026 DESC;

-- ============================================
-- REPORT 6: Offene Programme vs. geschlossene
-- ============================================
SELECT
    family,
    CASE
        WHEN SUM(CASE WHEN metric = 'Ord' THEN units END)
           = SUM(CASE WHEN metric = 'Del' THEN units END)
        THEN 'closed'
        ELSE 'open_backlog'
    END AS program_status,
    SUM(CASE WHEN metric = 'Ord' THEN units END)
      - SUM(CASE WHEN metric = 'Del' THEN units END) AS backlog
FROM fact_fleet_snapshot
GROUP BY family
ORDER BY backlog DESC;
