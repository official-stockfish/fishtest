#!/usr/bin/env python
"""
Command line interpreter using the expression line parser.

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

from __future__ import print_function

import cmd
import sys
import traceback
import expression

class Expression_Interpreter(cmd.Cmd):
    """
    Interactive command line interpreter that applies the expression line parser
    to the provided input.
    """

    def __init__(self):
        cmd.Cmd.__init__(self)
        self.prompt = '>> '
        self.parser = expression.Expression_Parser(assignment=True)

    def default(self, line):
        try:
            output = self.parser.parse(line)
            if output is not None:
                self.stdout.write(str(output) + '\n')

            variables = self.parser.variables
            variables.update(self.parser.modified_variables)
            self.parser.variables = variables
        except SyntaxError:
            traceback.print_exc(0)

    def do_quit(self, line):
        """
        Exit the interpreter.
        """

        if line != '' and line != '()':
            self.stdout.write(line + '\n')
        self._quit()

    @staticmethod
    def _quit():
        sys.exit(1)

def main():
    """
    Main entry point.
    """

    Expression_Interpreter().cmdloop()

if __name__ == '__main__':
    main()
