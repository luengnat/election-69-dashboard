# Minimal numpy stub for tests to avoid installing heavy native dependency.
import math
import statistics

pi = math.pi

def degrees(x):
    return math.degrees(x)

def median(seq):
    try:
        return statistics.median(seq)
    except Exception:
        # Fallback for empty or non-iterable
        return 0

def array(obj, dtype=None):
    return obj

def sum(obj, axis=None):
    try:
        if obj is None:
            return 0
        return builtin_sum(obj) if not hasattr(obj, 'sum') else obj.sum()
    except Exception:
        # naive fallback
        total = 0
        for v in obj:
            total += v
        return total

def var(obj, axis=None):
    try:
        if not obj:
            return 0
        mean = sum(obj) / len(obj)
        return sum((x - mean) ** 2 for x in obj) / len(obj)
    except Exception:
        return 0

# wrappers
builtin_sum = __builtins__['sum'] if isinstance(__builtins__, dict) else __builtins__.sum

__all__ = ['pi', 'degrees', 'median', 'array', 'sum', 'var']
