"""Local recognition calibrated against a labelled board supplied by the user."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image

START = [list(row) for row in (
    "rnbakabnr", ".........", ".c.....c.", "p.p.p.p.p", ".........",
    ".........", "P.P.P.P.P", ".C.....C.", ".........", "RNBAKABNR")]
LABELS = ".rnbakcpRNBAKCP"
REFERENCE = [list(row) for row in (
    "r...kab.r", "....a....", "..n.b.c.n", "p...p...p", ".c....p..",
    "..C.P....", "P.....P.P", "C.N...N..", ".........", ".RBAKABR.")]
REFERENCE_GEOMETRY = (231, 263, 741, 839)


@dataclass
class Geometry:
    left: float
    top: float
    right: float
    bottom: float
    red_bottom: bool = True

    @property
    def dx(self):
        return (self.right - self.left) / 8

    @property
    def dy(self):
        return (self.bottom - self.top) / 9

    def validate(self, size):
        width, height = size
        if not (0 <= self.left < self.right < width and 0 <= self.top < self.bottom < height):
            raise ValueError("棋盘定位超出截图范围，请重新点击两个棋盘角点。")
        if min(self.dx, self.dy) < 16 or not 0.65 < self.dx / self.dy < 1.5:
            raise ValueError("棋盘格距不合理，请点击左上和右下棋子的中心。")

    def screen_cell(self, row, col):
        if not self.red_bottom:
            row, col = 9 - row, 8 - col
        return self.left + col * self.dx, self.top + row * self.dy


def ink_mask(image, geometry, row, col):
    x, y = geometry.screen_cell(row, col)
    radius = min(geometry.dx, geometry.dy) * 0.30
    tile = image.crop((x-radius, y-radius, x+radius, y+radius)).convert("RGB")
    pixels = np.asarray(tile.resize((48, 48), Image.Resampling.BILINEAR)).astype(np.int16)
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    red_ink = (red-green > 35) & (red-blue > 35) & (green < 145) & (green-blue < (red-green)*0.75)
    dark_ink = (np.maximum(np.maximum(red, green), blue) < 115)
    mask = red_ink | dark_ink
    return mask, float(red_ink.sum()) / max(1, int(mask.sum()))


class Recognizer:
    def __init__(self, masks=None, labels=None):
        self.masks = masks
        self.labels = labels

    def calibrate(self, image, geometry, board=None):
        board = START if board is None else board
        geometry.validate(image.size)
        samples = [ink_mask(image, geometry, row, col)[0]
                   for row in range(10) for col in range(9)]
        self.masks = np.asarray(samples, dtype=bool)
        self.labels = np.asarray([piece for row in board for piece in row])
        # Detect obvious login pages, empty boards and inverted calibration.
        for side in (str.isupper, str.islower):
            selected = [sample.sum() for sample, label in zip(samples, self.labels)
                        if side(str(label))]
            if np.median(selected) < 90:
                self.masks = self.labels = None
                raise ValueError("棋子样本过少，请显示完整棋盘并核对红黑方向。")

    def save(self, path):
        np.savez_compressed(path, masks=self.masks, labels=self.labels)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            masks, labels = data["masks"], data["labels"]
        if masks.ndim != 3 or masks.shape[1:] != (48, 48) or labels.shape != (len(masks),) or not 90 <= len(masks) <= 500:
            raise ValueError("校准文件损坏，请重新校准。")
        return cls(masks.astype(bool), labels)

    def recognize(self, image, geometry):
        if self.masks is None:
            raise ValueError("请先用开局棋盘校准。")
        geometry.validate(image.size)
        board = [["."] * 9 for _ in range(10)]
        uncertain, scores = [], []
        template_count = self.masks.sum(axis=(1, 2))
        empty_limit = max(24, float(template_count[self.labels != "."].min())*0.25)
        for row in range(10):
            for col in range(9):
                mask, red_fraction = ink_mask(image, geometry, row, col)
                if mask.sum() < empty_limit:
                    best_label, best_score, margin = ".", 1.0, 1.0
                else:
                    allowed = np.asarray([
                        label == "." or (label.isupper() if red_fraction > 0.35 else label.islower())
                        for label in self.labels])
                    best = np.zeros(len(self.masks), dtype=float)
                    padded = np.pad(mask, 4)
                    for dy in (-4, -2, 0, 2, 4):
                        for dx in (-4, -2, 0, 2, 4):
                            shifted = padded[4+dy:52+dy, 4+dx:52+dx]
                            intersect = (self.masks & shifted).sum(axis=(1, 2))
                            denom = template_count + shifted.sum()
                            score = np.divide(2*intersect, denom, out=np.ones(len(self.masks)), where=denom != 0)
                            best = np.maximum(best, score)
                    classes = sorted([(float(best[(self.labels == label) & allowed].max()), label)
                                      for label in LABELS if np.any((self.labels == label) & allowed)], reverse=True)
                    best_score, best_label = classes[0]
                    margin = best_score - classes[1][0] if len(classes) > 1 else 1.0
                board[row][col] = best_label
                scores.append(best_score)
                if best_score < 0.68 or (margin < 0.045 and best_score < 0.995):
                    uncertain.append((row, col))
        return board, uncertain, scores


def to_fen(board, turn):
    if len(board) != 10 or any(len(row) != 9 for row in board):
        raise ValueError("棋盘必须是 9 列、10 行。")
    flat = [piece for row in board for piece in row]
    if any(piece not in LABELS for piece in flat):
        raise ValueError("存在未知棋子。")
    if flat.count("K") != 1 or flat.count("k") != 1:
        raise ValueError("必须各有一个红帅和黑将，请校正棋盘。")
    limits = {"K": 1, "A": 2, "B": 2, "N": 2, "R": 2, "C": 2, "P": 5}
    for label, limit in limits.items():
        if flat.count(label) > limit or flat.count(label.lower()) > limit:
            raise ValueError("棋子数量不合法，请校正棋盘。")
    for row in range(10):
        for col in range(9):
            label = board[row][col]
            if label == "K" and not (7 <= row <= 9 and 3 <= col <= 5):
                raise ValueError("红帅不在九宫内，请校正棋盘或方向。")
            if label == "k" and not (0 <= row <= 2 and 3 <= col <= 5):
                raise ValueError("黑将不在九宫内，请校正棋盘或方向。")
    kings = [(r, c) for r in range(10) for c in range(9) if board[r][c] in "Kk"]
    if kings[0][1] == kings[1][1] and all(board[r][kings[0][1]] == "."
                                        for r in range(kings[0][0]+1, kings[1][0])):
        raise ValueError("将帅照面，请校正棋盘。")
    rows = []
    for row in board:
        text, empty = "", 0
        for piece in row:
            if piece == ".":
                empty += 1
            else:
                if empty:
                    text += str(empty)
                    empty = 0
                text += piece
        if empty:
            text += str(empty)
        rows.append(text)
    if turn not in ("w", "b"):
        raise ValueError("请选择红方或黑方行棋。")
    return "/".join(rows) + " " + turn + " - - 0 1"


def describe_move(board, move):
    if len(move) != 4 or move == "0000":
        return "没有可用走法"
    c1, r1, c2, r2 = ord(move[0])-97, 9-int(move[1]), ord(move[2])-97, 9-int(move[3])
    names = {"r": "车", "n": "马", "b": "象", "a": "士", "k": "将", "c": "炮", "p": "卒",
             "R": "车", "N": "马", "B": "相", "A": "仕", "K": "帅", "C": "炮", "P": "兵"}
    piece = board[r1][c1]
    side = "红方" if piece.isupper() else "黑方"
    file1, file2 = (9-c1, 9-c2) if piece.isupper() else (c1+1, c2+1)
    if r1 == r2:
        verb, value = "平", file2
    else:
        forward = r2 < r1 if piece.isupper() else r2 > r1
        verb = "进" if forward else "退"
        value = file2 if piece.lower() in "nba" else abs(r2-r1)
    number = (lambda n: "一二三四五六七八九"[n-1]) if piece.isupper() else str
    same_file = [r for r in range(10) if board[r][c1] == piece]
    if len(same_file) == 2:
        front_row = min(same_file) if piece.isupper() else max(same_file)
        prefix = ("前" if r1 == front_row else "后") + names.get(piece, piece)
    else:
        prefix = names.get(piece, piece) + number(file1)
    return f"{side} {prefix}{verb}{number(value)}（{move}）"


def locate_board(image, red_bottom=True):
    """Find this board skin's tan panel. Refuse ambiguous/non-board screens."""
    scale = min(1.0, 900 / image.width)
    small = image.convert("RGB").resize((int(image.width*scale), int(image.height*scale)))
    pixels = np.asarray(small).astype(np.int16)
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    wood = (red > 170) & (green > 115) & (blue < 210) & (red-blue > 40) & (green-blue > 18)
    counts = wood.sum(axis=1)
    if counts.max() < small.width * 0.25:
        raise ValueError("未找到棋盘。请显示完整棋盘或手动定位。")
    indices = np.flatnonzero(counts > counts.max()*0.45)
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > 8)+1)
    groups = [group for group in groups if len(group) > 60]
    if not groups:
        raise ValueError("未找到连续棋盘区域，请手动定位。")
    group = max(groups, key=len)
    top, bottom = int(group[0]), int(group[-1])
    columns = np.flatnonzero(wood[top:bottom+1].mean(axis=0) > 0.60)
    column_groups = np.split(columns, np.flatnonzero(np.diff(columns) > 8)+1)
    column_groups = [group for group in column_groups if len(group) > 60]
    if not column_groups:
        raise ValueError("棋盘左右边界不明确，请手动定位。")
    group = max(column_groups, key=len)
    left, right = int(group[0]), int(group[-1])
    width, height = right-left, bottom-top
    if not 0.80 < width/height < 1.06:
        raise ValueError("检测区域不是完整象棋棋盘，请手动定位。")
    geometry = Geometry((left+width*0.065)/scale, (top+height*0.050)/scale,
                        (left+width*0.937)/scale, (top+height*0.940)/scale, red_bottom)
    geometry.validate(image.size)
    return geometry
