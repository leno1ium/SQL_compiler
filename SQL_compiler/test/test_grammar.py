# test_grammar.py
from pathlib import Path
from lark import Lark

# Загружаем грамматику
grammar_path = Path(__file__).parent / '../parser/parser.lark'
grammar = grammar_path.read_text(encoding='utf-8')

print("Проверка грамматики...")
try:
    # Пробуем создать парсер
    parser = Lark(grammar, start="start", parser="lalr")
    print("✅ Грамматика корректна!")

    # Тестовые запросы
    test_queries = [
        """SELECT DISTINCT u.name, COUNT(o.id) as order_count
    FROM users u
    INNER JOIN orders o ON u.id = o.user_id
    WHERE u.age > 18 
      AND u.city IN ('Moscow', 'SPB')
      AND o.status LIKE '%completed%'
    GROUP BY u.name
    HAVING COUNT(o.id) > 5
    ORDER BY order_count DESC
    LIMIT 20 OFFSET 10""",
    ]

    for query in test_queries:
        try:
            tree = parser.parse(query)
            print(f"✅ Успешно разобрано: {query[:30]}...")

        except Exception as e:
            print(f"❌ Ошибка в запросе '{query}': {e}")

except Exception as e:
    print(f"❌ Ошибка в грамматике: {e}")

    # Выводим проблемную строку
    lines = grammar.split('\n')
    for i, line in enumerate(lines, 1):
        if '(' in line and not line.strip().startswith('//'):
            print(f"Строка {i}: {line}")