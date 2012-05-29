"""
Code generator module. Subclass CodeGen to implement a code generator
as a visitor.
"""

import minivisitor

class CodeGen(minivisitor.TreeVisitor):
    def __init__(self, context, codewriter):
        super(CodeGen, self).__init__(context)
        self.code = codewriter

    def results(self, *nodes):
        results = []
        for childlist in nodes:
            result = self.visit_childlist(childlist)
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)

        return tuple(results)

    def visitchild(self, node):
        if node is None:
            return
        return self.visit(node)

class CodeGenCleanup(CodeGen):
    def visit_Node(self, node):
        self.visitchildren(node)

    def visit_ForNode(self, node):
        # The body has already been disposed of
        self.visit(node.init)
        self.visit(node.condition)
        self.visit(node.step)

class CCodeGen(CodeGen):

    label_counter = 0

    def __init__(self, context, codewriter):
        super(CCodeGen, self).__init__(context, codewriter)
        self.declared_temps = set()

    def visit_FunctionNode(self, node):
        code = self.code

        name = code.mangle(node.name + node.specialization_name)
        node.mangled_name = name

        args = self.results(node.arguments)
        proto = "static int %s(%s)" % (name, ", ".join(args))
        code.proto_code.putln(proto + ';')
        code.putln("%s {" % proto)
        code.declaration_point = code.insertion_point()
        self.visitchildren(node)
        code.putln("}")

    def visit_FunctionArgument(self, node):
        typename = self.context.declare_type
        return ", ".join("%s %s" % (typename(v.type), self.visit(v))
                             for v in node.variables)

    def visit_StatListNode(self, node):
        self.visitchildren(node)
        return node

    def visit_ForNode(self, node):
        code = self.code

        error_handler = None
        if node.body.may_error(self.context):
            error_handler = self.context.error_handler(code)

        exprs = self.results(node.init, node.condition, node.step)
        code.putln("for (%s; %s; %s) {" % exprs)

        if not node.is_tiled:
            self.code.declaration_levels.append(code.insertion_point())
            self.code.loop_levels.append(code.insertion_point())

        self.visit(node.init)
        self.visit(node.body)

        if error_handler:
            error_handler.catch_here(code)
            disposal_point = code.insertion_point()
            error_handler.cascade(code)
        else:
            disposal_point = code

        self.context.generate_disposal_code(code, node.body)

        if not node.is_tiled:
            self.code.declaration_levels.pop()
            self.code.loop_levels.pop()

        code.putln("}")

    def visit_ReturnNode(self, node):
        self.code.putln("return %s;" % self.results(node.operand))

    def visit_BinopNode(self, node):
        return "(%s %s %s)" % (self.visit(node.lhs),
                               node.operator,
                               self.visit(node.rhs))

    def visit_UnopNode(self, node):
        return "(%s%s)" % (node.operator, self.visit(node.operand))

    def visit_TempNode(self, node):
        name = self.code.mangle(node.name)
        if name not in self.declared_temps:
            self.declared_temps.add(name)
            code = self.code.declaration_point
            code.putln("%s %s;" % (self.context.declare_type(node.type), name))

        return name

    def visit_AssignmentExpr(self, node):
        return "%s = %s" % self.results(node.lhs, node.rhs)

    def visit_AssignmentNode(self, node):
        self.code.putln(self.visit(node.operand) + ';')

    def visit_CastNode(self, node):
        return "((%s) %s)" % (self.context.declare_type(node.type),
                              self.visit(node.operand))

    def visit_DereferenceNode(self, node):
        return "(*%s)" % self.visit(node.operand)

    def visit_SingleIndexNode(self, node):
        return "(%s[%s])" % self.results(node.lhs, node.rhs)

    def visit_ArrayAttribute(self, node):
        return node.name

    def visit_Variable(self, node):
        return self.code.mangle(node.name)

    def visit_JumpNode(self, node):
        self.code.putln("goto %s;" % self.results(node.label))

    def visit_JumpTargetNode(self, node):
        self.code.putln("%s:" % self.results(node.label))

    def visit_LabelNode(self, node):
        if node.mangled_name is None:
            node.mangled_name = "%s%d" % (node.name, self.label_counter)
            self.label_counter += 1
        return node.mangled_name

    def visit_ConstantNode(self, node):
        return str(node.value)

#    def visit_ErrorHandler(self, node):
#        self.visitchild(node.error_var_init)
#        self.visit(node.body)
#        self.visit(node.label)
#        self.visitchild()
