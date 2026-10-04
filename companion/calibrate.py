"""Build local recognition templates from a user-owned initial-position screenshot."""
import argparse
import sys
from pathlib import Path
from PIL import Image
from vision import START, Geometry, Recognizer, locate_board

def main():
    # Windows non-Chinese redirected consoles may otherwise use cp1252.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="使用完整开局棋盘截图生成本机识别模板")
    parser.add_argument("image", type=Path, help="本机 PNG/JPG/BMP 截图路径")
    parser.add_argument("--red-top", action="store_true", help="截图中红方在上")
    parser.add_argument("--corners", type=float, nargs=4, metavar=("LEFT","TOP","RIGHT","BOTTOM"),
                        help="自动定位失败时指定左上、右下交点中心坐标")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "templates.npz")
    args = parser.parse_args()
    with Image.open(args.image) as source:
        image = source.convert("RGB")
    geometry = Geometry(*args.corners, not args.red_top) if args.corners else locate_board(image, not args.red_top)
    recognizer = Recognizer()
    recognizer.calibrate(image, geometry, START)
    board, uncertain, _ = recognizer.recognize(image, geometry)
    if board != START or uncertain:
        raise SystemExit("校准未通过：必须是双方各 16 子、尚未走棋的完整开局；检查方向、皮肤和角点。")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    recognizer.save(args.output)
    print("已生成本机模板："+str(args.output))

if __name__ == "__main__":
    main()
