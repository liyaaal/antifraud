-- Полезные запросы к журналу (неделя 5). Запуск: psql_db.bat или
--   docker compose exec db psql -U antifraud -d antifraud

-- 1. Сколько операций в базе и сколько из них помечено как фрод
SELECT count(*) AS operations, sum(is_fraud_pred) AS flagged FROM transactions;

-- 2. Success rate и ошибки /predict за последние 5 минут
SELECT avg((status_code < 400)::int) AS success_rate,
       count(*) AS requests,
       count(*) FILTER (WHERE status_code = 422) AS errors_422
FROM request_log
WHERE endpoint = '/predict' AND ts > now() - interval '5 minutes';

-- 3. Fraud rate по модели и фактический, качество по меткам
SELECT avg(t.is_fraud_pred) AS fraud_rate_model,
       avg(l.is_fraud)      AS fraud_rate_actual,
       count(l.is_fraud)    AS labeled,
       count(*) FILTER (WHERE t.is_fraud_pred = 1 AND l.is_fraud = 1) AS tp,
       count(*) FILTER (WHERE t.is_fraud_pred = 1 AND l.is_fraud = 0) AS fp,
       count(*) FILTER (WHERE t.is_fraud_pred = 0 AND l.is_fraud = 1) AS fn
FROM transactions t
LEFT JOIN labels l ON l.transaction_id = t.id;

-- 4. Сколько операций дороже 500 у.е. модель пометила как фрод за последние 10 минут
SELECT count(*) FROM transactions
WHERE is_fraud_pred = 1 AND amount > 500 AND received_at > now() - interval '10 minutes';

-- 5. Последние 20 срабатываний с меткой
SELECT t.received_at, t.card_id, t.category, t.amount, t.fraud_score, l.is_fraud
FROM transactions t LEFT JOIN labels l ON l.transaction_id = t.id
WHERE t.is_fraud_pred = 1
ORDER BY t.received_at DESC LIMIT 20;

-- 6. Последние ошибки
SELECT ts, endpoint, status_code, error FROM request_log
WHERE status_code >= 400 ORDER BY ts DESC LIMIT 10;

-- 7. Поиск по полю из payload (JSONB): все операции одного магазина
SELECT received_at, amount, fraud_score FROM transactions
WHERE payload->>'merchant' = 'fraud_Kunde-Sanford';

-- 8. Проверка, что индекс используется
EXPLAIN ANALYZE
SELECT avg((status_code < 400)::int), count(*) FROM request_log
WHERE endpoint = '/predict' AND ts > now() - interval '5 minutes';
