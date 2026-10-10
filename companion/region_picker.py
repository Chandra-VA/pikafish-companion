"""One-shot local desktop grid selector. Pixels stay in memory."""
import ctypes
from ctypes import wintypes
import json
import sys
import tkinter as tk
from PIL import ImageTk
from capture import setup_dpi, desktop_rect, capture_rect, region_from_grid, user32


def pick_region():
    setup_dpi()
    bounds = desktop_rect()
    image = capture_rect(bounds)
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{image.width}x{image.height}+0+0")
    canvas = tk.Canvas(root, width=image.width, height=image.height, highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(image)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    hint = tk.Label(root, text="拖动：最左上交叉点 → 最右下交叉点（棋子中心）｜Enter 确认｜Esc 取消",
                    bg="#17283b", fg="white", font=("Microsoft YaHei UI", 14), padx=20, pady=12)
    # Keep the instruction on the primary display even with left-hand monitors.
    hint.place(x=-bounds[0]+40, y=-bounds[1]+24)
    start, selection, result = [None], [None], [None]

    def draw(event):
        if start[0] is None:
            return
        x1, y1 = start[0]
        x2, y2 = max(0, min(image.width-1, event.x)), max(0, min(image.height-1, event.y))
        x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
        selection[0] = (x1, y1, x2, y2)
        canvas.delete("grid")
        for col in range(9):
            x = x1+(x2-x1)*col/8
            canvas.create_line(x, y1, x, y2, fill="#20f6ba", width=1, tags="grid")
        for row in range(10):
            y = y1+(y2-y1)*row/9
            canvas.create_line(x1, y, x2, y, fill="#20f6ba", width=1, tags="grid")
        canvas.create_rectangle(x1, y1, x2, y2, outline="#20f6ba", width=3, tags="grid")

    def begin(event):
        start[0] = (event.x, event.y)
        draw(event)

    def confirm(unused=None):
        if selection[0] is None:
            return
        try:
            x1, y1, x2, y2 = selection[0]
            result[0] = region_from_grid((x1+bounds[0], y1+bounds[1], x2+bounds[0], y2+bounds[1]), bounds)
            root.destroy()
        except ValueError as error:
            hint.config(text=str(error)+"｜重新拖动｜Esc 取消")

    canvas.bind("<ButtonPress-1>", begin)
    canvas.bind("<B1-Motion>", draw)
    canvas.bind("<ButtonRelease-1>", draw)
    root.bind("<Return>", confirm)
    root.bind("<Escape>", lambda unused: root.destroy())
    root.update_idletasks()
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    hwnd = user32.GetAncestor(root.winfo_id(), 2)
    user32.SetWindowPos(hwnd, None, bounds[0], bounds[1], image.width, image.height, 0x0040)
    root.focus_force()
    root.after(180000, root.destroy)
    root.mainloop()
    return result[0]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps({"selection": pick_region()}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        sys.exit(1)
