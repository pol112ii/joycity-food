# -*- coding: utf-8 -*-
"""
재료 인식 진단 도구 (클릭 없음, 화면 읽기만).

인벤토리를 한 번 스캔해서:
  - 각 칸이 어떤 재료로 인식됐는지 (또는 빈칸/미인식)
  - 등록된 각 재료가 인벤토리에서 가장 잘 맞은 차이값
을 표로 출력함. 쌀이 왜 안 잡히는지 이 숫자로 판단.

실행 후 결과를 그대로 복사해서 알려주면 됨.
"""

import os

# ===================== 설정값 (auto_cook.py와 동일) =====================
CELL1_CENTER = (2843, 67)
PITCH_X = 41.6          # ([1,6]x - [1,1]x)/5 = (3051-2843)/5
PITCH_Y = 41.25         # ([5,1]y - [1,1]y)/4 = (232-67)/4
COLS = 6
ROWS = 5
CELL_SIZE = 32
SEARCH_MARGIN = 4       # 계산된 칸 위치가 어긋나도 실제 아이콘 중심을 스스로 찾는 여유 범위
                        # (너무 넓으면 옆 칸까지 침범함)

MATCH_THRESHOLD = 50    # 기본 인식 기준 (auto_cook.py와 동일)
MATCH_THRESHOLDS = {}


def threshold_for(name):
    return MATCH_THRESHOLDS.get(name, MATCH_THRESHOLD)
TOP_CUT = 13            # 위쪽 수량숫자 영역을 가림 (이 픽셀 수만큼 위를 무시)
SHIFT = 2               # 좌표 미세 어긋남 보정 (±픽셀)
# ======================================================================


def locate_true_center(sct, nominal_cx, nominal_cy):
    """계산된 칸 중심 근처를 넓게 캡처해서 실제 아이콘(밝은 픽셀)의 중심을 찾음."""
    import numpy as np
    m = SEARCH_MARGIN
    size = CELL_SIZE + 2 * m
    nx, ny = int(round(nominal_cx)), int(round(nominal_cy))
    shot = sct.grab({"left": nx - size // 2, "top": ny - size // 2,
                      "width": size, "height": size})
    img = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
    bright = img.sum(axis=2) > 90
    ys, xs = np.nonzero(bright)
    if len(ys) < 20:
        return nominal_cx, nominal_cy, False
    true_cx = nx - size // 2 + int(xs.mean())
    true_cy = ny - size // 2 + int(ys.mean())
    return true_cx, true_cy, True


def match_diff(cell, tpl):
    """cell(32x32)과 tpl(32x32)의 차이값.

    위쪽 숫자영역 제외 + ±SHIFT 흔들림 보정 + 검은 배경이 아닌 부분(그림이
    있는 부분)만 골라서 비교. 배경끼리는 항상 잘 맞아떨어져서 그대로 평균 내면
    진짜 그림 차이가 희석되는 문제가 있었음.
    """
    import numpy as np
    m = SHIFT
    H, W = cell.shape[:2]
    base = cell[TOP_CUT + m:H - m, m:W - m]
    best = 1e9
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            comp = tpl[TOP_CUT + m + dy:H - m + dy, m + dx:W - m + dx]
            if comp.shape != base.shape:
                continue
            fg = (base.sum(axis=2) > 90) | (comp.sum(axis=2) > 90)
            if fg.sum() < 20:
                continue
            d = np.abs(base[fg] - comp[fg]).mean()
            if d < best:
                best = d
    return best


def main():
    import mss
    import numpy as np
    from PIL import Image

    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items")
    templates = {}
    if os.path.isdir(folder):
        for fn in os.listdir(folder):
            if not fn.lower().endswith(".png") or fn.startswith("cell_"):
                continue
            name = os.path.splitext(fn)[0]
            img = np.array(Image.open(os.path.join(folder, fn)).convert("RGB"), dtype=int)
            templates[name] = img[:CELL_SIZE, :CELL_SIZE]

    if not templates:
        print("[문제] items 폴더에 등록된 재료 이미지가 없습니다.")
        print(f"       확인할 폴더: {folder}")
        return

    print("등록된 재료:", ", ".join(templates))
    print(f"인식 기준: 기본 {MATCH_THRESHOLD} 이하 (재료별 예외: {MATCH_THRESHOLDS})\n")

    half = CELL_SIZE // 2
    # 각 재료별 최소 차이값 추적
    best_for = {name: (1e9, None) for name in templates}

    with mss.mss() as sct:
        print("칸별 인식 결과 (행,열 → 인식결과 [차이값]):")
        for r in range(ROWS):
            line = []
            for c in range(COLS):
                nominal_cx = CELL1_CENTER[0] + c * PITCH_X
                nominal_cy = CELL1_CENTER[1] + r * PITCH_Y
                cx, cy, has_item = locate_true_center(sct, nominal_cx, nominal_cy)
                if not has_item:
                    line.append("[빈칸]")
                    continue
                shot = sct.grab({"left": cx - half, "top": cy - half,
                                 "width": CELL_SIZE, "height": CELL_SIZE})
                cell = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
                bn, bd = None, 1e9
                for name, tpl in templates.items():
                    diff = match_diff(cell, tpl)
                    if diff < bd:
                        bn, bd = name, diff
                    if diff < best_for[name][0]:
                        best_for[name] = (diff, (r + 1, c + 1))
                if bn is not None and bd <= threshold_for(bn):
                    line.append(f"{bn}({bd:.0f})")
                else:
                    line.append(f"?({bn}:{bd:.0f})")
            print(f" {r+1}행: " + "  ".join(line))

    print("\n재료별 '가장 잘 맞은 칸' 요약:")
    for name, (diff, where) in best_for.items():
        verdict = "인식 O" if diff <= threshold_for(name) else "인식 X (기준 초과)"
        print(f"  {name:12s} 최소차이 {diff:5.1f}  위치 {where}  → {verdict}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
