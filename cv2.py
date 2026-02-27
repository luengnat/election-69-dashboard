# Minimal cv2 stub for tests that only need imports.
# Functions return None or simple defaults so high-level modules can import.

# Basic image read/write

def imread(path, flags=None):
    return None


def imwrite(path, img):
    return False

# Edge and contour helpers (no-ops)

def Canny(*args, **kwargs):
    return None

def cvtColor(img, code):
    return None

def HoughLines(*args, **kwargs):
    return None

def getRotationMatrix2D(center, angle, scale):
    return None

def warpAffine(img, M, dsize, flags=None, borderMode=None):
    return img


def adaptiveThreshold(*args, **kwargs):
    return None

def getStructuringElement(*args, **kwargs):
    return None

def morphologyEx(img, op, kernel, iterations=1):
    return None

def addWeighted(*args, **kwargs):
    return None

def threshold(img, thresh, maxval, type):
    return (None, None)

def findContours(img, mode, method):
    return ([], None)

def boundingRect(c):
    return (0, 0, 0, 0)

# Constants used by repository
COLOR_BGR2GRAY = 6
ADAPTIVE_THRESH_GAUSSIAN_C = 1
THRESH_BINARY_INV = 16
MORPH_RECT = 0
MORPH_OPEN = 2
RETR_TREE = 0
CHAIN_APPROX_SIMPLE = 0
TM_CCOEFF_NORMED = 0
BORDER_REPLICATE = 0
INTER_CUBIC = 2
THRESH_BINARY = 8

# Expose a simple cv2 interface
__all__ = [
    'imread', 'imwrite', 'Canny', 'cvtColor', 'HoughLines', 'getRotationMatrix2D',
    'warpAffine', 'adaptiveThreshold', 'getStructuringElement', 'morphologyEx',
    'addWeighted', 'threshold', 'findContours', 'boundingRect'
]
