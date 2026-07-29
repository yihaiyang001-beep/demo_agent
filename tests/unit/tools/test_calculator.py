from __future__ import annotations

import pytest
from pydantic import ValidationError

from mini_agent.domain.errors import ToolExecutionError
from mini_agent.tools.calculator import CalculatorArgs, CalculatorTool


def execute(expression, runtime_context):
    return CalculatorTool().execute(CalculatorArgs(expression=expression), runtime_context)


def test_calculator_basic(runtime_context):
    assert execute("123 * 456", runtime_context)["result"] == 56088


def test_calculator_parentheses(runtime_context):
    assert execute("(12 + 3) * 4", runtime_context)["result"] == 60


def test_calculator_division_by_zero(runtime_context):
    with pytest.raises(ToolExecutionError) as exc_info:
        execute("10 / 0", runtime_context)
    assert exc_info.value.code == "DIVISION_BY_ZERO"


@pytest.mark.parametrize("expression", ["abs(-1)", "__import__('os')", "open('x')"])
def test_calculator_rejects_function_call(runtime_context, expression):
    with pytest.raises(ToolExecutionError) as exc_info:
        execute(expression, runtime_context)
    assert exc_info.value.code == "UNSAFE_EXPRESSION"


def test_calculator_rejects_attribute_access(runtime_context):
    with pytest.raises(ToolExecutionError) as exc_info:
        execute("(1).real", runtime_context)
    assert exc_info.value.code == "UNSAFE_EXPRESSION"


def test_calculator_rejects_large_power(runtime_context):
    with pytest.raises(ToolExecutionError) as exc_info:
        execute("2 ** 11", runtime_context)
    assert exc_info.value.code == "EXPONENT_TOO_LARGE"


def test_calculator_rejects_long_expression():
    with pytest.raises(ValidationError):
        CalculatorArgs(expression="1" * 201)

