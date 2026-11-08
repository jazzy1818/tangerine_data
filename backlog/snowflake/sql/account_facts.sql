-- Executed by the website in Snowflake. All table names use the configured schema.
-- Medians use all history; balance uses the last six observations per account.
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY month DESC) AS rn
    FROM monthly_history
), cutoff AS (
    SELECT DATEADD(month, -11, MAX(month)) AS recent_start FROM monthly_history
), baseline AS (
    SELECT account_id, MEDIAN(money_in) AS money_in, MEDIAN(money_out) AS money_out,
           AVG(CASE WHEN rn <= 6 THEN avg_daily_balance END) AS buffer,
           TO_CHAR(MAX(month), 'YYYY-MM') AS last_month
    FROM ranked GROUP BY account_id
), recent AS (
    SELECT account_id, COUNT(*) AS recent_months,
           SUM(CASE WHEN money_out > money_in THEN 1 ELSE 0 END) AS deficit_months,
           SUM(CASE WHEN days_below_zero > 0 THEN 1 ELSE 0 END) AS negative_months,
           SUM(CASE WHEN days_below_zero > 0 AND month_end_balance IS NOT NULL THEN 1 ELSE 0 END) AS eligible_negative_months,
           SUM(CASE WHEN days_below_zero > 0 AND month_end_balance >= 0 THEN 1 ELSE 0 END) AS recovered_months
    FROM monthly_history CROSS JOIN cutoff WHERE month >= recent_start
    GROUP BY account_id
)
SELECT b.*, COALESCE(l.status, 'NONE') AS loan_status,
       COALESCE(r.recent_months, 0) AS recent_months,
       COALESCE(r.deficit_months, 0) AS deficit_months,
       COALESCE(r.negative_months, 0) AS negative_months,
       COALESCE(r.eligible_negative_months, 0) AS eligible_negative_months,
       COALESCE(r.recovered_months, 0) AS recovered_months
FROM baseline b LEFT JOIN recent r ON b.account_id = r.account_id
LEFT JOIN loan_snapshot l ON b.account_id = l.account_id
ORDER BY b.account_id
