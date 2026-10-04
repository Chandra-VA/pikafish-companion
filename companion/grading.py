"""Compare a played move with a root search in native UCI integer score units."""
from engine import analyze, parse_info
from variation import evaluation


def grade_move(fen, history, move, turn, seconds, cancel):
    def search(forced=None):
        infos = []
        def callback(line):
            info = parse_info(line)
            if info and info["rank"] == 1 and not info.get("bound"):
                infos.append(info)
        best = analyze(fen, seconds, callback, cancel, history, 1, searchmoves=forced)
        if not infos:
            raise ValueError("搜索未返回可比较的评估值")
        return best, infos[-1]

    best_move, best = search()
    chosen = best if move == best_move else search([move])[1]
    result = {"status": "done", "bestmove": best_move, "move": move,
              "best_evaluation": evaluation(best, turn), "played_evaluation": evaluation(chosen, turn),
              "best_depth": best["depth"], "played_depth": chosen["depth"], "seconds": seconds,
              "best_score": best["score"] * (1 if turn == "w" else -1) if best["unit"] == "cp" else None,
              "played_score": chosen["score"] * (1 if turn == "w" else -1) if chosen["unit"] == "cp" else None,
              "best_mate": best["score"] * (1 if turn == "w" else -1) if best["unit"] == "mate" else None,
              "played_mate": chosen["score"] * (1 if turn == "w" else -1) if chosen["unit"] == "mate" else None,
              "score_unit": "cp", "loss": None}
    if move == best_move:
        result.update(loss=0, label="引擎首选")
    elif best["unit"] == chosen["unit"] == "cp":
        loss = max(0, best["score"]-chosen["score"])
        result.update(loss=loss, label="与首选评估相当" if loss == 0 else "偏离首选")
    elif chosen["unit"] == "mate" and chosen["score"] > 0:
        result.update(label="保持将杀" if best["unit"] == "mate" else "找到将杀")
    elif chosen["unit"] == "mate" and chosen["score"] <= 0:
        result.update(label="仍在被将杀变化中" if best["unit"] == "mate" and best["score"] < 0 else "进入被将杀变化")
    else:
        result.update(label="未保持引擎的将杀变化")
    return result
