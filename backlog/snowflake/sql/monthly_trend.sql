SELECT TO_CHAR(month, 'YYYY-MM') AS month, COUNT(*) AS accounts,
       SUM(CASE WHEN money_out > money_in THEN 1 ELSE 0 END) AS deficit_accounts,
       SUM(money_in) AS total_inflow, SUM(money_out) AS total_spending
FROM monthly_history
WHERE month >= (SELECT DATEADD(month, -11, MAX(month)) FROM monthly_history)
GROUP BY month ORDER BY month
