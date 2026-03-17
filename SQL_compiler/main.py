import os
import parser


def main():

    # prog = parser.parse(prog)
    # print(*prog.tree, sep=os.linesep)
    parser.print_ast("""
    SELECT u.name, o.total 
    FROM users u 
    JOIN orders o ON u.id = o.user_id
    """)


if __name__ == "__main__":
    main()
