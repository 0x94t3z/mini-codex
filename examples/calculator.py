#!/usr/bin/env python3
"""
Simple command-line calculator.
Supports addition, subtraction, multiplication, division.
"""

def add(a, b):
    return a + b

def sub(a, b):
    return a - b

def mul(a, b):
    return a * b

def div(a, b):
    if b == 0:
        raise ValueError("Division by zero!")
    return a / b

def main():
    operations = {
        '+': add,
        '-': sub,
        '*': mul,
        '/': div,
    }

    while True:
        expr = input("Enter expression (or 'quit' to exit): ").strip()
        if expr.lower() == 'quit':
            print("Goodbye!")
            break

        try:
            parts = expr.split()
            if len(parts) != 3:
                raise ValueError("Invalid format. Use: <number> <op> <number>")

            left = float(parts[0])
            op = parts[1]
            right = float(parts[2])

            if op not in operations:
                raise ValueError(f"Unsupported operator: {op}")

            result = operations[op](left, right)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()