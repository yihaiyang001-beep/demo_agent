"""AST-whitelisted arithmetic calculator."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

from pydantic import Field

from mini_agent.domain.errors import ToolExecutionError
from mini_agent.domain.models import ToolRuntimeContext

from .base import BaseTool, ToolArgs

MAX_AST_NODES = 100
MAX_EXPONENT = 10
MAX_ABS_RESULT = 1e100


class CalculatorArgs(ToolArgs):
    expression: str = Field(
        min_length=1,
        max_length=200,
        description="需要计算的数学表达式，例如 (12 + 3) * 4",
    )


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Safely evaluate a basic arithmetic expression."
    args_model = CalculatorArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, CalculatorArgs)
        expression = args.expression
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ToolExecutionError(
                "INVALID_EXPRESSION",
                "数学表达式语法无效",
                str(exc),
            ) from exc

        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            raise ToolExecutionError(
                "EXPRESSION_TOO_COMPLEX",
                "数学表达式过于复杂",
            )

        try:
            result = self._evaluate(tree.body)
        except ZeroDivisionError as exc:
            raise ToolExecutionError(
                "DIVISION_BY_ZERO",
                "数学表达式包含除以零",
            ) from exc
        except (OverflowError, ValueError) as exc:
            raise ToolExecutionError(
                "RESULT_OUT_OF_RANGE",
                "计算结果超出允许范围",
                str(exc),
            ) from exc

        return {"expression": expression, "result": result}

    def _evaluate(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ToolExecutionError(
                    "UNSAFE_EXPRESSION",
                    "表达式只能包含数字和基本算术运算",
                )
            return self._check_result(node.value)

        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            value = self._evaluate(node.operand)
            return self._check_result(_UNARY_OPERATORS[type(node.op)](value))

        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise ToolExecutionError(
                    "EXPONENT_TOO_LARGE",
                    f"幂指数绝对值不能超过 {MAX_EXPONENT}",
                )
            result = _BINARY_OPERATORS[type(node.op)](left, right)
            return self._check_result(result)

        raise ToolExecutionError(
            "UNSAFE_EXPRESSION",
            "表达式只能包含数字、括号和 + - * / // % ** 运算",
        )

    @staticmethod
    def _check_result(value: int | float) -> int | float:
        if abs(value) > MAX_ABS_RESULT:
            raise ToolExecutionError(
                "RESULT_OUT_OF_RANGE",
                "计算结果绝对值不能超过 1e100",
            )
        return value

