from SQL_compiler.parser.parser import print_ast

tests = [
    """SELECT DISTINCT 
    u.id,
    u.name AS user_name,
    u.email,
    u.age,
    COUNT(*) AS order_count,
    SUM(o.total) AS total_spent,
    AVG(o.total) AS avg_order_value,
    MIN(o.created_at) AS first_order,
    MAX(o.created_at) AS last_order
FROM users u
LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'completed'
INNER JOIN order_items oi ON o.id = oi.order_id
RIGHT JOIN products p ON oi.product_id = p.id
CROSS JOIN categories c
WHERE u.age > 18
  AND u.age < 65
  AND u.city IN ('Moscow', 'SPB', 'Kazan', 'Novosibirsk')
  AND u.email LIKE '%@gmail.com'
  AND u.email NOT LIKE '%test%'
  AND o.total BETWEEN 100 AND 5000
  AND o.total NOT BETWEEN 0 AND 99
  AND o.status IS NOT NULL
  AND p.price IS NOT NULL
  AND c.name IN ('Electronics', 'Clothing')
  AND c.name NOT IN ('Toys', 'Food')
  AND EXISTS (SELECT 1 FROM payments pay WHERE pay.order_id = o.id)
  AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id = o.id)
GROUP BY u.id, u.name, u.email, u.age
HAVING COUNT(o.id) > 3
   AND COUNT(o.id) < 20
   AND SUM(o.total) > 1000
   AND SUM(o.total)  BETWEEN 0 AND 999
   AND AVG(o.total) BETWEEN 100 AND 500
   AND AVG(o.total)  BETWEEN 0 AND 99
ORDER BY total_spent DESC, last_order ASC, u.name DESC
LIMIT 50 OFFSET 10;""",

    """SELECT 
    p.category,
    COUNT(o.user_id) AS unique_buyers,
    MIN(p.price) * 1.1 AS min_with_tax,
    MAX(p.price) - 5 AS max_discounted,
    AVG(p.price) + 10 AS avg_plus_margin,
    SUM(o.quantity) % 100 AS quantity_mod
FROM products p
RIGHT JOIN order_items oi ON p.id = oi.product_id
CROSS JOIN categories c
WHERE NOT (p.price < 10 OR p.price > 1000)
  AND p.name LIKE '%phone%'
  AND p.name NOT LIKE '%case%'
  AND p.id IN (101, 202, 303)
  AND p.id NOT IN (404, 505)
  AND oi.discount IS NULL
  AND oi.total BETWEEN 50 AND 500
GROUP BY p.category
HAVING COUNT(*) < 100
   AND SUM(oi.quantity) NOT BETWEEN 0 AND 9
   AND AVG(p.price) > 50
ORDER BY unique_buyers DESC
LIMIT 20;""",
]

for i, test in enumerate(tests, 1):
    print(f"\n{'=' * 60}")
    print(f"ТЕСТ {i}: {test}")
    print(f"{'=' * 60}")
    print_ast(test)
