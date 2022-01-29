"""
Sandboxed expression parser.

Copyright 2017-2018 Leon Helwerda

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# Use Python 3 division
from __future__ import division
import ast

class Expression_Parser(ast.NodeVisitor):
    """
    Transformer that safely parses an expression, disallowing any complicated
    functions or control structures (inline if..else is allowed though).
    """

    # Boolean operators
    # The AST nodes may have multiple ops and right comparators, but we
    # evaluate each op individually.
    _boolean_ops = {
        ast.And: lambda left, right: left and right,
        ast.Or: lambda left, right: left or right
    }

    # Binary operators
    _binary_ops = {
        ast.Add: lambda left, right: left + right,
        ast.Sub: lambda left, right: left - right,
        ast.Mult: lambda left, right: left * right,
        ast.Div: lambda left, right: left / right,
        ast.Mod: lambda left, right: left % right,
        ast.Pow: lambda left, right: left ** right,
        ast.LShift: lambda left, right: left << right,
        ast.RShift: lambda left, right: left >> right,
        ast.BitOr: lambda left, right: left | right,
        ast.BitXor: lambda left, right: left ^ right,
        ast.BitAnd: lambda left, right: left & right,
        ast.FloorDiv: lambda left, right: left // right
    }

    # Unary operators
    _unary_ops = {
        ast.Invert: lambda operand: ~operand,
        ast.Not: lambda operand: not operand,
        ast.UAdd: lambda operand: +operand,
        ast.USub: lambda operand: -operand
    }

    # Comparison operators
    # The AST nodes may have multiple ops and right comparators, but we
    # evaluate each op individually.
    _compare_ops = {
        ast.Eq: lambda left, right: left == right,
        ast.NotEq: lambda left, right: left != right,
        ast.Lt: lambda left, right: left < right,
        ast.LtE: lambda left, right: left <= right,
        ast.Gt: lambda left, right: left > right,
        ast.GtE: lambda left, right: left >= right,
        ast.Is: lambda left, right: left is right,
        ast.IsNot: lambda left, right: left is not right,
        ast.In: lambda left, right: left in right,
        ast.NotIn: lambda left, right: left not in right
    }

    # Predefined variable names
    _variable_names = {
        'True': True,
        'False': False,
        'None': None
    }

    # Predefined functions
    _function_names = {
        'int': int,
        'float': float,
        'bool': bool
    }

    def __init__(self, variables=None, functions=None, assignment=False):
        self._variables = None
        self.variables = variables

        if functions is None:
            self._functions = {}
        else:
            self._functions = functions

        self._assignment = False
        self.assignment = assignment

        self._used_variables = set()
        self._modified_variables = {}

    def parse(self, expression, filename='<expression>'):
        """
        Parse a string `expression` and return its result.
        """

        self._used_variables = set()
        self._modified_variables = {}

        try:
            return self.visit(ast.parse(expression))
        except SyntaxError as error:
            error.filename = filename
            error.text = expression
            raise error
        except Exception as error:
            error_type = error.__class__.__name__
            if len(error.args) > 2:
                line_col = error.args[1:]
            else:
                line_col = (1, 0)

            error = SyntaxError('{}: {}'.format(error_type, error.args[0]),
                                (filename,) + line_col + (expression,))
            raise error

    @property
    def variables(self):
        """
        Retrieve the variables that exist in the scope of the parser.

        This property returns a copy of the dictionary.
        """

        return self._variables.copy()

    @variables.setter
    def variables(self, variables):
        """
        Set a new variable scope for the expression parser.

        If built-in keyword names `True`, `False` or `None` are used, then
        this property raises a `NameError`.
        """

        if variables is None:
            variables = {}
        else:
            variables = variables.copy()

        variable_names = set(variables.keys())
        constant_names = set(self._variable_names.keys())
        forbidden_variables = variable_names.intersection(constant_names)
        if forbidden_variables:
            keyword = 'keyword' if len(forbidden_variables) == 1 else 'keywords'
            forbidden = ', '.join(forbidden_variables)
            raise NameError('Cannot override {} {}'.format(keyword, forbidden))

        self._variables = variables

    @property
    def assignment(self):
        """
        Retrieve whether assignments are accepted by the parser.
        """

        return self._assignment

    @assignment.setter
    def assignment(self, value):
        """
        Enable or disable parsing assignments.
        """

        self._assignment = bool(value)

    @property
    def used_variables(self):
        """
        Retrieve the names of the variables that were evaluated in the most
        recent call to `parse`. If `parse` failed with an exception, then
        this set may be incomplete.
        """

        return self._used_variables

    @property
    def modified_variables(self):
        """
        Retrieve the variables that were set or modified in the most recent call
        to `parse`. Since only one expression is allowed, this dictionary
        contains at most one element. An augmented expression such as `+=` is
        used, then the variable is only in this dictionary if the variable
        is in the scope. If `parse` failed with any other exception, then
        this dictionary may be incomplete. If the expression parser is set to
        disallow assignments, then the dictionary is always empty.

        This property returns a copy of the dictionary.
        """

        return self._modified_variables.copy()

    def generic_visit(self, node):
        """
        Visitor for nodes that do not have a custom visitor.

        This visitor denies any nodes that may not be part of the expression.
        """

        raise SyntaxError('Node {} not allowed'.format(ast.dump(node)),
                          ('', node.lineno, node.col_offset, ''))

    def visit_Module(self, node):
        """
        Visit the root module node.
        """

        if len(node.body) != 1:
            if len(node.body) > 1:
                lineno = node.body[1].lineno
                col_offset = node.body[1].col_offset
            else:
                lineno = 1
                col_offset = 0

            raise SyntaxError('Exactly one expression must be provided',
                              ('', lineno, col_offset, ''))

        return self.visit(node.body[0])

    def visit_Expr(self, node):
        """
        Visit an expression node.
        """

        return self.visit(node.value)

    def visit_BoolOp(self, node):
        """
        Visit a boolean expression node.
        """

        op = type(node.op)
        func = self._boolean_ops[op]
        result = func(self.visit(node.values[0]), self.visit(node.values[1]))
        for value in node.values[2:]:
            result = func(result, self.visit(value))

        return result

    def visit_BinOp(self, node):
        """
        Visit a binary expression node.
        """

        op = type(node.op)
        func = self._binary_ops[op]
        return func(self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node):
        """
        Visit a unary expression node.
        """

        op = type(node.op)
        func = self._unary_ops[op]
        return func(self.visit(node.operand))

    def visit_IfExp(self, node):
        """
        Visit an inline if..else expression node.
        """

        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_Compare(self, node):
        """
        Visit a comparison expression node.
        """

        result = self.visit(node.left)
        for operator, comparator in zip(node.ops, node.comparators):
            op = type(operator)
            func = self._compare_ops[op]
            result = func(result, self.visit(comparator))

        return result

    def visit_Call(self, node):
        """
        Visit a function call node.
        """

        name = node.func.id
        if name in self._functions:
            func = self._functions[name]
        elif name in self._function_names:
            func = self._function_names[name]
        else:
            raise NameError("Function '{}' is not defined".format(name),
                            node.lineno, node.col_offset)

        args = [self.visit(arg) for arg in node.args]
        keywords = dict([self.visit(keyword) for keyword in node.keywords])

        # Python 2.7 starred arguments
        if hasattr(node, 'starargs') and hasattr(node, 'kwargs'):
            if node.starargs is not None or node.kwargs is not None:
                raise SyntaxError('Star arguments are not supported',
                                  ('', node.lineno, node.col_offset, ''))

        return func(*args, **keywords)

    def visit_Assign(self, node):
        """
        Visit an assignment node.
        """

        if not self.assignment:
            raise SyntaxError('Assignments are not allowed in this expression',
                              ('', node.lineno, node.col_offset, ''))

        if len(node.targets) != 1:
            raise SyntaxError('Multiple-target assignments are not supported',
                              ('', node.lineno, node.col_offset, ''))
        if not isinstance(node.targets[0], ast.Name):
            raise SyntaxError('Assignment target must be a variable name',
                              ('', node.lineno, node.col_offset, ''))

        name = node.targets[0].id
        self._modified_variables[name] = self.visit(node.value)

    def visit_AugAssign(self, node):
        """
        Visit an augmented assignment node.
        """

        if not self.assignment:
            raise SyntaxError('Assignments are not allowed in this expression',
                              ('', node.lineno, node.col_offset, ''))

        if not isinstance(node.target, ast.Name):
            raise SyntaxError('Assignment target must be a variable name',
                              ('', node.lineno, node.col_offset, ''))

        name = node.target.id
        if name not in self._variables:
            raise NameError("Assignment name '{}' is not defined".format(name),
                            node.lineno, node.col_offset)

        op = type(node.op)
        func = self._binary_ops[op]
        self._modified_variables[name] = func(self._variables[name],
                                              self.visit(node.value))

    def visit_Starred(self, node):
        """
        Visit a starred function keyword argument node.
        """

        # pylint: disable=no-self-use

        raise SyntaxError('Star arguments are not supported',
                          ('', node.lineno, node.col_offset, ''))

    def visit_keyword(self, node):
        """
        Visit a function keyword argument node.
        """

        if node.arg is None:
            raise SyntaxError('Star arguments are not supported',
                              ('', node.lineno, node.col_offset, ''))

        return (node.arg, self.visit(node.value))

    def visit_Num(self, node):
        """
        Visit a literal number node.
        """

        # pylint: disable=no-self-use
        return node.n

    def visit_Name(self, node):
        """
        Visit a named variable node.
        """

        if node.id in self._variables:
            self._used_variables.add(node.id)
            return self._variables[node.id]

        if node.id in self._variable_names:
            return self._variable_names[node.id]

        raise NameError("Name '{}' is not defined".format(node.id),
                        node.lineno, node.col_offset)

    def visit_NameConstant(self, node):
        """
        Visit a named constant singleton node (Python 3).
        """

        # pylint: disable=no-self-use
        return node.value
