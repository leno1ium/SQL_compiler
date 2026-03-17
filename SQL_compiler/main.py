import os
import parser


def main():

    # prog = parser.parse(prog)
    # print(*prog.tree, sep=os.linesep)
    parser.print_ast("""
    SELECT name, age FROM users WHERE age >= 18;
    """)


if __name__ == "__main__":
    main()
