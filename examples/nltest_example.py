"""Example: Generate Tests from Natural Language.

Write test requirements in plain English and get executable Python code.
"""

from agentprobe.nltest import NLTestGenerator


def main():
    gen = NLTestGenerator()

    # Translate individual assertions
    assertion = gen.translate("The agent should respond in under 5 seconds")
    if assertion:
        print(gen.render_translation(assertion))
        # 📝 "The agent should respond in under 5 seconds"
        # →  assertions.latency_below(recording, max_ms=5000)
        #    Confidence: [█████████░] 90%

    # Generate a complete test
    test = gen.generate_test("test_customer_support", [
        "The agent should respond in under 5 seconds",
        "The agent must not use more than $0.10",
        "The agent should call the search tool at least once",
        "The output should not be empty",
        "No PII should be in the output",
    ])

    print(gen.render_test(test))

    # Write to file
    gen.write_test_file("tests/test_generated.py", [test])
    print("\nTest written to tests/test_generated.py")


if __name__ == "__main__":
    main()
