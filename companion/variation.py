"""Translate and replay the engine's actual variation, without inventing future moves."""
from copy import deepcopy
from engine import valid_move
from vision import describe_move


def replay(board, moves, turn):
    position = deepcopy(board)
    positions, descriptions = [deepcopy(position)], []
    for move in moves:
        if not valid_move(move):
            raise ValueError("后续着法格式不合法")
        c1, r1, c2, r2 = ord(move[0])-97, 9-int(move[1]), ord(move[2])-97, 9-int(move[3])
        piece, destination = position[r1][c1], position[r2][c2]
        if piece == "." or piece.isupper() != (turn == "w") or (destination != "." and destination.isupper() == piece.isupper()):
            raise ValueError("后续变化与当前棋盘不一致")
        descriptions.append(describe_move(position, move).split("（", 1)[0])
        position[r1][c1], position[r2][c2] = ".", piece
        positions.append(deepcopy(position))
        turn = "b" if turn == "w" else "w"
    return positions, descriptions


def evaluation(info, turn):
    score = info["score"] * (1 if turn == "w" else -1)
    if info["unit"] == "mate":
        if score == 0:
            return "当前行棋方已被将死"
        return ("红方" if score > 0 else "黑方") + f"有将杀，距离 {abs(score)}（引擎报告）"
    bound = info.get("bound")
    if turn == "b" and bound:
        bound = "upperbound" if bound == "lowerbound" else "lowerbound"
    prefix = {"lowerbound": "≥", "upperbound": "≤"}.get(bound, "")
    advantage = "接近均势" if abs(score) < 25 else ("红方占优" if score > 0 else "黑方占优")
    return f"红分 {prefix}{score:+d} · {advantage}"


def variation_text(descriptions):
    return "\n".join(f"{index//2+1}. " + " → ".join(descriptions[index:index+2])
                     for index in range(0, len(descriptions), 2))
