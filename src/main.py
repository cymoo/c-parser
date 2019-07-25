import os
import pickle
import sys
from abc import ABC, abstractmethod
from functools import reduce
from os.path import join as p_join, abspath, isabs, dirname
from types import GeneratorType

from clang.cindex import *
from pprint import pprint
from tu_flag import TranslationUnitFlags
from utils import equal_slice, catch_error


def get_all_compile_commands(path: str) -> GeneratorType:
    """从compile_commands.json中获取编译选项，并将相对路径转为绝对路径"""
    db = CompilationDatabase.fromDirectory(path)
    commands = db.getAllCompileCommands()
    for cmd in commands:
        directory = cmd.directory
        arguments = []
        for arg in cmd.arguments:
            if arg.startswith('-I') and arg[2] != '/':
                arguments.append('-I' + abspath(p_join(directory, arg[2:])))
            else:
                arguments.append(arg)
        if not isabs(arguments[-1]):
            arguments[-1] = abspath(p_join(directory, arguments[-1]))
        yield arguments


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
    def handle_simple(self, commands):
        index = Index.create(self.excluded_decls)
        for cmd in commands:
            tu = TranslationUnit.from_source(
                None,
                args=cmd,
                index=index,
                options=self.visitor.tu_flag
            )
            self.traverse(tu.cursor)
        self.visitor.store()

    def handle_fork(self, commands, num):
        slices = equal_slice(commands, num)
        pids = []

        for idx in range(num):
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
                self.visitor.store()
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

    # Python标准库中的方法均无效，得自行调用fork处理
    # 1. multiprocessing.Pool: ctypes objects containing pointers cannot be pickled
    # 2. concurrent.futures.ProcessPoolExecutor: dead lock
    def run(self, commands: list, use_fork=True):
        cpus = os.cpu_count()
        # 当待分析的文件较少时，单进程即可
        if len(commands) < cpus or not use_fork:
            self.handle_simple(commands)
        # 多进程处理
        else:
            self.handle_fork(commands, os.cpu_count())

        self.visitor.merge()


class Visitor(ABC):
    # 每个visitor可能需要不同的flag，比如仅寻找函数声明时，无需解析函数体
    tu_flag = 0
    # 是否打印详细信息，比如访问每个文件前，输出文件名
    verbose = False

    _TMP_DIR = p_join(dirname(abspath((dirname(__file__)))), 'data/tmp')

    @classmethod
    def set_tu_flag(cls, flag: int = 0):
        """设置翻译选项"""
        cls.tu_flag = flag

    def visit(self, node: Cursor):
        """访问每个节点，产生数据"""
        if self.verbose:
            if node.kind == Cursor.TRANSLATION_UNIT:
                print(node.spelling, file=sys.stderr)

    @staticmethod
    def dump(data, dirname, filename):
        """使用pickle系列化数据至指定的文件中"""
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(p_join(dirname, filename), 'wb') as fp:
            pickle.dump(data, fp, protocol=pickle.HIGHEST_PROTOCOL)

    @abstractmethod
    def store(self):
        """保存子进程产生的所有数据"""

    @staticmethod
    def load_from_dir(directory) -> list:
        """把一个目录下所有由pickle.dump序列化的数据load进列表中"""
        ml = []
        for file in os.listdir(directory):
            with open(p_join(directory, file), 'rb') as fp:
                ml.append(pickle.load(fp))
        return ml

    @abstractmethod
    def merge(self):
        """合并所有子进程产生的数据，并进行去重，过滤，筛选等处理"""


class MacroVisitor(Visitor):
    """寻找未被使用的宏"""

    tu_flag = TranslationUnitFlags.DetailedPreprocessingRecord | \
              TranslationUnitFlags.SkipFunctionBodies

    def __init__(self):
        # 同一个头文件可能会被多次include，为了防止出现重复，须使用set，做好的方式是使用PCH
        self.decls = set()
        self.refs = set()
        self._md_dir = p_join(self._TMP_DIR, 'md', str(int(time.time())))
        self._mr_dir = p_join(self._TMP_DIR, 'mr', str(int(time.time())))

    @catch_error(ValueError)
    def visit(self, node: Cursor):
        super().visit(node)

        # 筛选宏定义，且宏不是通过编译选项指定
        if node.kind == CursorKind.MACRO_DEFINITION and node.location.file:
            location = node.location
            self.decls.add((
                node.displayname,
                location.line,
                location.column,
                abspath(location.file.name)
            ))

        # 筛选宏展开，且宏不是内置宏
        if node.kind == CursorKind.MACRO_INSTANTIATION and not node.is_macro_builtin():
            node1 = node.get_definition()
            location1 = node1.location

            # 如果file为空，则宏是编译器插入的，所以无需处理
            if not location1.file:
                return

            self.refs.add((
                node1.displayname,
                node1.location.line,
                node1.location.column,
                abspath(location1.file.name)
            ))

    def store(self):
        self.dump(self.decls, self._md_dir, str(os.getpid()))
        self.dump(self.refs, self._mr_dir, str(os.getpid()))

    def merge(self):

        def reducer(s1: set, s2: set) -> set:
            return s1.union(s2)

        decls = reduce(reducer, self.load_from_dir(self._md_dir), set())
        refs = reduce(reducer, self.load_from_dir(self._mr_dir), set())
        unused = [
            {'name': item[0], 'line': item[1], 'col': item[2], 'file': item[3]}
            for item in (decls - refs) if not self.macro_from_sys(item[0], item[3])
        ]
        # test
        pprint(unused)

    @staticmethod
    def macro_from_sys(name: str, fpath: str) -> bool:
        return fpath.startswith('/usr') or fpath.startswith('/Library')


class TypedefVisitor(Visitor):
    """寻找未被使用的typedef"""


class GlobalVarDeclVisitor(Visitor):
    """寻找全局变量声明和定义"""


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
    cdb = '/Users/cymoo/Documents/github/clang/cmake-build-debug'
    # cdb = '../c-test/build'
    t1 = time.time()
    visitor = MacroVisitor()
    analyzer = Analyzer(
        clang_lib_path='/usr/local/llvm/lib',
        visitor=visitor
    )
    analyzer.run(list(get_all_compile_commands(cdb)), use_fork=True)
    t2 = time.time()
    print('time used: {}'.format(t2 - t1))
