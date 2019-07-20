from abc import ABC, abstractmethod
from enum import IntEnum
from clang.cindex import *


class Visitor(ABC):
    @abstractmethod
    def process(self, node: Cursor):
        """处理每个节点"""

    @abstractmethod
    def post_process(self):
        """处理完全部的翻译单元后，进行筛选分析等"""


# http://clang.llvm.org/doxygen/Index_8h_source.html
class TranslationUnitFlags(IntEnum):
    None_ = 0x0
    # Used to indicate that the parser should construct a "detailed" preprocessing record,
    # including all macro definitions and instantiations.
    DetailedPreprocessingRecord = 0x01
    Incomplete = 0x02
    PrecompiledPreamble = 0x04
    CacheCompletionResults = 0x08
    ForSerialization = 0x10
    CXXChainedPCH = 0x20
    # Used to indicate that function/method bodies should be skipped while parsing.
    # This option can be used to search for declarations/definitions while  ignoring the usages.
    SkipFunctionBodies = 0x40
    IncludeBriefCommentsInCodeCompletion = 0x80
    CreatePreambleOnFirstParse = 0x100
    # Do not stop processing when fatal errors are encountered.
    KeepGoing = 0x200
    SingleFileParse = 0x400
    LimitSkipFunctionBodiesToPreamble = 0x800
    IncludeAttributedTypes = 0x1000
    VisitImplicitAttributes = 0x2000
    IgnoreNonErrorsFromIncludedFiles = 0x4000


class Analyzer:
    def __init__(self,
                 clang_lib_path: str,
                 compilation_database_dir: str = None,
                 tu_flags: int = TranslationUnitFlags.DetailedPreprocessingRecord.value,
                 excluded_decls: bool = False):
        Config.set_library_path(clang_lib_path)
        self.index = Index.create(excluded_decls)
        self.commands = []
        self._visitors = []
        self._compilation_db_dir = compilation_database_dir
        self._tu_flags = tu_flags

    def add_visitor(self, visitor: Visitor):
        self._visitors.append(visitor)

    def add_compile_commands(self, cmd: [list, str]):
        if isinstance(cmd, str):
            cmd = cmd.split()
        self.commands.append(cmd)

    def add_compile_commands_from_database(self):
        if self._compilation_db_dir is None:
            return
        db = CompilationDatabase.fromDirectory(self._compilation_db_dir)
        commands = db.getAllCompileCommands()
        for cmd in commands:
            self.commands.append(list(cmd.arguments))

    def traverse(self, node: Cursor):
        for visitor in self._visitors:
            visitor.process(node)
        for child in node.get_children():
            self.traverse(child)

    # Multiprocessing cannot be used: ctypes objects containing pointers cannot be pickled
    # Yes, Python is awesome!
    def run(self):
        self.add_compile_commands_from_database()
        for cmd in self.commands:
            tu = TranslationUnit.from_source(None, args=cmd, index=self.index, options=self._tu_flags)
            self.traverse(tu.cursor)
        for visitor in self._visitors:
            visitor.post_process()


class MacroVisitor(Visitor):
    def __init__(self):
        self.defined_macro = {}
        self.expanded_marco = {}

    def process(self, node: Cursor):
        if node.kind == CursorKind.MACRO_DEFINITION:
            print('macro definition: {}'.format(node.displayname))
        if node.kind == CursorKind.MACRO_INSTANTIATION:
            pass

    def post_process(self):
        print('process macro done')


class CallExprVisitor(Visitor):
    pass


class VarExprVisitor(Visitor):
    pass


class CXXMethodVisitor(Visitor):
    pass


class ClassDeclVisitor(Visitor):
    pass


if __name__ == '__main__':
    analyzer = Analyzer(
        clang_lib_path='/usr/local/llvm/lib',
        compilation_database_dir='../c-test/build'
    )
    analyzer.add_visitor(MacroVisitor())
    analyzer.run()
