tests = [

    "SELECT * FROM users;",
    "SELECT id, name FROM users;",
    "SELECT name AS user_name FROM users;",
    "SELECT DISTINCT city FROM users;",

    # 2. WHERE операторы
    "SELECT name FROM users WHERE age > 25;",
    "SELECT name FROM users WHERE age >= 18;",
    "SELECT name FROM users WHERE age = 30;",
    "SELECT name FROM users WHERE age != 25;",

    # 3. LIKE
    #"SELECT name FROM users WHERE name LIKE 'A';",
    #"SELECT name FROM users WHERE name NOT LIKE '%x%';",

    # 4. IN
    "SELECT name FROM users WHERE city IN ('Moscow', 'SPB');",
    #"SELECT name FROM users WHERE city NOT IN ('Moscow', 'SPB');",

    # 5. BETWEEN
    "SELECT name FROM users WHERE age BETWEEN 18 AND 65;",
    #"SELECT name FROM users WHERE age NOT BETWEEN 18 AND 65;",

    # 6. IS NULL
    #"SELECT name FROM users WHERE email IS NULL;",
    #"SELECT name FROM users WHERE email IS NOT NULL;",

    # 7. AND/OR
    #"SELECT name FROM users WHERE age > 18 AND city = 'Moscow';",
    #"SELECT name FROM users WHERE age > 18 OR city = 'Moscow';",

    # 8. JOIN
    "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id;",
    "SELECT u.name FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
    "SELECT u.name FROM users u RIGHT JOIN orders o ON u.id = o.user_id;",
    #"SELECT u.name, p.name FROM users u CROSS JOIN products p;",

    # 9. GROUP BY
    #"SELECT city, COUNT(*) FROM users GROUP BY city;",
    #"SELECT city, COUNT(*) FROM users GROUP BY city HAVING COUNT(*) > 5;",

    # 10. ORDER BY и LIMIT
    "SELECT name FROM users ORDER BY age;",
    "SELECT name FROM users ORDER BY age DESC;",
    "SELECT name FROM users ORDER BY age DESC, name ASC;",
    "SELECT name FROM users LIMIT 10;",
    "SELECT name FROM users LIMIT 10 OFFSET 5;",
]