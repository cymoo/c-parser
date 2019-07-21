from abc import ABC, abstractmethod, abstractclassmethod
from clang.cindex import *
from enum import IntEnum
from functools import wraps
import os
import sys
from types import GeneratorType

# 防止递归深度超过默认最大值999
sys.setrecursionlimit(9999)


def get_all_compile_commands(path: str) -> GeneratorType:
    """从compile_commands.json中获取编译选项"""
    db = CompilationDatabase.fromDirectory(path)
    commands = db.getAllCompileCommands()
    for cmd in commands:
        yield list(cmd.arguments)


def equal_slice(items: list, num: int) -> callable:
    """将items均分num份"""
    chunk_size = len(items) // num

    def chunk(idx: int):
        if idx < 0 or idx >= num:
            raise ValueError('idx should be in {}...{}'.format(0, num-1))
        if idx == num - 1:
            return items[idx * chunk_size:]
        return items[idx * chunk_size: (idx+1) * chunk_size]
    return chunk


def catch_error(err_type=Exception):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kw):
            try:
                return func(*args, **kw)
            except err_type as e:
                print(e, file=sys.stderr, flush=True)
        return wrapped
    return wrapper


# http://clang.llvm.org/doxygen/Index_8h_source.html
class TranslationUnitFlags(IntEnum):
    """控制翻译的行为"""
    None_ = 0x0
    # Used to indicate that the parser should construct a "detailed" preprocessing record,
    # including all macro definitions and instantiations.
    DetailedPreprocessingRecord = 0x01
    Incomplete = 0x02
    # Used to indicate that the translation unit should be built with an implicit precompiled header for the preamble.
    PrecompiledPreamble = 0x04
    CacheCompletionResults = 0x08
    # Used to indicate that the translation unit will be serialized with clang_saveTranslationUnit.
    # This option is typically used when parsing a header with the intent of producing a precompiled header.
    ForSerialization = 0x10
    # DEPRECATED
    CXXChainedPCH = 0x20
    # Used to indicate that function/method bodies should be skipped while parsing.
    # This option can be used to search for declarations/definitions while  ignoring the usages.
    SkipFunctionBodies = 0x40
    IncludeBriefCommentsInCodeCompletion = 0x80
    # Used to indicate that the precompiled preamble should be created on the first parse.
    # Otherwise it will be created on the first reparse. This trades runtime on the first parse (serializing the preamble takes time)
    # for reduced runtime on the second parse (can now reuse the preamble).
    CreatePreambleOnFirstParse = 0x100
    # Do not stop processing when fatal errors are encountered.
    KeepGoing = 0x200
    # Sets the preprocessor in a mode for parsing a single file only.
    SingleFileParse = 0x400
    # Used in combination with CXTranslationUnit_SkipFunctionBodies to constrain the skipping of function bodies to the preamble.
    LimitSkipFunctionBodiesToPreamble = 0x800
    # Used to indicate that attributed types should be included in CXType.
    IncludeAttributedTypes = 0x1000
    # Used to indicate that implicit attributes should be visited.
    VisitImplicitAttributes = 0x2000
    # Used to indicate that non-errors from included files should be ignored.
    IgnoreNonErrorsFromIncludedFiles = 0x4000


class Analyzer:
    """解析的入口
    :param clang_lib_path: The directory of libclang.so
    :param excluded_decls_from_pch: This process of creating the 'pre-compiled header (PCH)', loading it separately,
           and using it (via -include-pch) allows 'excludeDeclsFromPCH' to remove redundant callbacks.
           more info about pch, see <http://clang.llvm.org/docs/PCHInternals.html>
    """
    def __init__(self,
                 clang_lib_path: str,
                 visitor,
                 excluded_decls_from_pch: bool = False):
        Config.set_library_path(clang_lib_path)
        self.excluded_decls = excluded_decls_from_pch
        self.visitor = visitor

    def traverse(self, node: Cursor):
        self.visitor.visit(node)
        for child in node.get_children():
            self.traverse(child)

    # Python中现有的并行方案都没法使用，得自行调用fork进行处理
    # 1. multiprocessing.Pool: ctypes objects containing pointers cannot be pickled
    # 2. concurrent.futures.ThreadPoolExecutor: GIL
    # 3. concurrent.futures.ProcessPoolExecutor: dead lock
    def run(self, commands: list, use_fork=True):
        cpus = os.cpu_count()
        cmd_len = len(commands)
        # 当待分析的文件较少时，单进程即可
        if cmd_len < cpus or not use_fork:
            index = Index.create(self.excluded_decls)
            for cmd in commands:
                tu = TranslationUnit.from_source(
                    None,
                    args=cmd,
                    index=index,
                    options=self.visitor.tu_flag
                )
                self.traverse(tu.cursor)
        # 多进程处理
        else:
            slices = equal_slice(commands, cpus)
            pids = []
            for idx in range(cpus):
                pid = os.fork()
                if pid == 0:
                    # NOTE: 每个进程应独立创建index，否则可能会发生未预期的行为
                    index = Index.create(self.excluded_decls)
                    for cmd in slices(idx):
                        tu = TranslationUnit.from_source(
                            None,
                            args=cmd,
                            index=index,
                            options=self.visitor.tu_flag
                        )
                        self.traverse(tu.cursor)
                    sys.exit(0)
                else:
                    pids.append(pid)

            while len(pids):
                # TODO: waitpid 在 MacOS 10.14.5下会等待所有进程结束后才返回，与linux下不一样？
                pid, status = os.waitpid(-1, 0)
                # this shall not happen...
                if pid == -1 or pid == 0:
                    print('sys error', file=sys.stderr)
                    return
                else:
                    pids.remove(pid)

            self.visitor.after_visits()


class Visitor(ABC):
    tu_flag = 0

    @classmethod
    def set_tu_flag(cls, flag: int = 0):
        """设置翻译选项"""
        cls.tu_flag = flag

    @abstractmethod
    def visit(self, node: Cursor):
        """访问每个节点，并进行相应处理"""

    @abstractmethod
    def after_visits(self):
        """处理完全部的翻译单元后，进行筛选分析等"""


class MacroVisitor(Visitor):
    """寻找所有的宏定义和展开"""
    tu_flag = TranslationUnitFlags.DetailedPreprocessingRecord | \
              TranslationUnitFlags.SkipFunctionBodies

    def __init__(self):
        self.defined_macro = {}
        self.expanded_marco = {}

    @catch_error(Exception)
    def visit(self, node: Cursor):
        if node.kind == CursorKind.MACRO_DEFINITION:
            print(node.displayname)
        if node.kind == CursorKind.MACRO_INSTANTIATION:
            pass

    def after_visits(self):
        pass


class GlobalVarDeclVisitor(Visitor):
    """寻找全局变量声明和定义"""
    tu_flag = TranslationUnitFlags.SkipFunctionBodies

    def __init__(self):
        self.vars = {}

    @catch_error(Exception)
    def visit(self, node: Cursor):
        if (node.kind == CursorKind.VAR_DECL) and \
           (node.lexical_parent.kind == CursorKind.TRANSLATION_UNIT):
            location = node.location
            print('vars: {} <{} : {}> in [{}]'.format(
                node.displayname,
                location.line,
                location.column,
                location.file
            ))

    def after_visits(self):
        pass


class FunctionDeclVisitor(Visitor):
    """寻找函数声明和定义"""


class CallExprVisitor(Visitor):
    """寻找所有的函数调用"""


class CXXMethodVisitor(Visitor):
    """寻找C++方法声明和定义"""


class ClassDeclVisitor(Visitor):
    """寻找C++类声明和定义"""


if __name__ == '__main__':
    import time
    db_path = '/Users/cymoo/Documents/github/clang/cmake-build-debug'

    t1 = time.time()
    visitor = MacroVisitor()
    analyzer = Analyzer(
        clang_lib_path='/usr/local/llvm/lib',
        visitor=visitor
    )
    analyzer.run(list(get_all_compile_commands(db_path)), use_fork=True)
    t2 = time.time()
    print('time used: {}'.format(t2 - t1))
