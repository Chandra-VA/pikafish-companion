"""Desktop pixels within the visible 天天象棋 window, using Win32 GDI."""
import ctypes
from ctypes import wintypes
from PIL import Image

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def setup_dpi():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def list_game_windows():
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    @callback_type
    def enum(hwnd, unused):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd)+1)
        user32.GetWindowTextW(hwnd, title, len(title))
        if "天天象棋" in title.value:
            found.append((int(hwnd), title.value))
        return True

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(enum, 0)
    return found


def window_rect(hwnd):
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    return rect.left, rect.top, rect.right, rect.bottom


def board_visible(hwnd, geometry):
    left, top, _, _ = window_rect(hwnd)
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    for row, col in ((row, col) for row in range(10) for col in range(9)):
        x, y = geometry.screen_cell(row, col)
        visible = user32.WindowFromPoint(wintypes.POINT(int(left+x), int(top+y)))
        if user32.GetAncestor(visible, 2) != hwnd:
            return False
    return True


def capture_game(hwnd=None):
    found = list_game_windows()
    if hwnd is None:
        if len(found) != 1:
            raise RuntimeError("请选择正在显示天天象棋的浏览器窗口。")
        hwnd = found[0][0]
    if hwnd not in [item[0] for item in found]:
        raise RuntimeError("窗口已关闭或已切换标签，请回到天天象棋并重新选择窗口。")
    if user32.IsIconic(hwnd):
        raise RuntimeError("天天象棋已最小化，请恢复窗口。")
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    width, height = right-left, bottom-top
    if width <= 0 or height <= 0 or width*height > 30_000_000:
        raise RuntimeError("窗口尺寸异常，请改用导入截图。")
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    screen = user32.GetDC(None)
    if not screen:
        raise RuntimeError("无法读取桌面画面。")
    memory, bitmap, old = None, None, None
    try:
        memory = gdi32.CreateCompatibleDC(screen)
        if not memory:
            raise RuntimeError("创建截图上下文失败")
        header = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader), width, -height,
                                  1, 32, 0, width*height*4, 0, 0, 0, 0)
        buffer = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(screen, ctypes.byref(header), 0,
                                        ctypes.byref(buffer), None, 0)
        if not bitmap or not buffer.value:
            raise RuntimeError("创建截图缓冲区失败")
        old = gdi32.SelectObject(memory, bitmap)
        if not gdi32.BitBlt(memory, 0, 0, width, height, screen, left, top, 0x00CC0020 | 0x40000000):
            raise ctypes.WinError(ctypes.get_last_error())
        pixels = ctypes.string_at(buffer, width*height*4)
        return Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX")
    finally:
        if old:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
