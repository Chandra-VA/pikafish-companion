"""Xiangqi movement and king-safety rules for local practice moves."""
from copy import deepcopy
from engine import valid_move


def squares(move):
    if not isinstance(move, str) or not valid_move(move):
        raise ValueError("着法格式不合法")
    return 9-int(move[1]), ord(move[0])-97, 9-int(move[3]), ord(move[2])-97


def palace(row, col, red):
    return 3 <= col <= 5 and (7 <= row <= 9 if red else 0 <= row <= 2)


def pseudo_legal(board, move, attack=False):
    r1, c1, r2, c2 = squares(move)
    piece, target = board[r1][c1], board[r2][c2]
    if piece == "." or (r1, c1) == (r2, c2):
        return False
    red = piece.isupper()
    if target != "." and target.isupper() == red:
        return False
    if not attack and target.lower() == "k":
        return False
    dr, dc = r2-r1, c2-c1
    kind = piece.lower()
    if kind in ("r", "c") or (kind == "k" and attack and target.lower() == "k" and c1 == c2):
        if dr and dc:
            return False
        sr, sc = (0 if dr == 0 else (1 if dr > 0 else -1)), (0 if dc == 0 else (1 if dc > 0 else -1))
        distance = max(abs(dr), abs(dc))
        blockers = sum(board[r1+i*sr][c1+i*sc] != "." for i in range(1, distance))
        return blockers == (1 if kind == "c" and target != "." else 0)
    if kind == "n":
        if (abs(dr), abs(dc)) not in ((2, 1), (1, 2)):
            return False
        leg_r, leg_c = (r1+dr//2, c1) if abs(dr) == 2 else (r1, c1+dc//2)
        return board[leg_r][leg_c] == "."
    if kind == "b":
        return (abs(dr) == abs(dc) == 2 and (r2 >= 5 if red else r2 <= 4)
                and board[r1+dr//2][c1+dc//2] == ".")
    if kind == "a":
        return abs(dr) == abs(dc) == 1 and palace(r2, c2, red)
    if kind == "k":
        return abs(dr)+abs(dc) == 1 and palace(r2, c2, red)
    if kind == "p":
        return (dc == 0 and dr == (-1 if red else 1)) or (dr == 0 and abs(dc) == 1 and (r1 <= 4 if red else r1 >= 5))
    return False


def in_check(board, turn):
    king = "K" if turn == "w" else "k"
    positions = [(r, c) for r in range(10) for c in range(9) if board[r][c] == king]
    if len(positions) != 1:
        return True
    kr, kc = positions[0]
    for r in range(10):
        for c in range(9):
            piece = board[r][c]
            if piece != "." and piece.isupper() != (turn == "w"):
                move = f"{chr(97+c)}{9-r}{chr(97+kc)}{9-kr}"
                if pseudo_legal(board, move, attack=True):
                    return True
    return False


def apply_move(board, move, turn):
    r1, c1, r2, c2 = squares(move)
    piece = board[r1][c1]
    if turn not in ("w", "b") or piece == "." or piece.isupper() != (turn == "w"):
        raise ValueError("请走当前行棋方的棋子。")
    if not pseudo_legal(board, move):
        raise ValueError("这一步不符合象棋走法规则。")
    position = deepcopy(board)
    position[r1][c1], position[r2][c2] = ".", piece
    if in_check(position, turn):
        raise ValueError("这一步会使己方将帅受将，或造成将帅照面。")
    return position


def legal_moves(board, turn=None):
    moves = []
    for r in range(10):
        for c in range(9):
            piece = board[r][c]
            if piece == "." or (turn and piece.isupper() != (turn == "w")):
                continue
            side = "w" if piece.isupper() else "b"
            for target_r in range(10):
                for target_c in range(9):
                    move = f"{chr(97+c)}{9-r}{chr(97+target_c)}{9-target_r}"
                    if pseudo_legal(board, move):
                        try:
                            apply_move(board, move, side)
                            moves.append(move)
                        except ValueError:
                            pass
    return moves
