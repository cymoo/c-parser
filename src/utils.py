import os
import pickle
import sys
import time
from functools import wraps
from contextlib import contextmanager


@contextmanager
def timeit(msg):
    """计算一段代码执行的时长"""
    t0 = time.time()
    try:
        yield
    finally:
        print('{}: {} s'.format(msg, time.time() - t0))


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
