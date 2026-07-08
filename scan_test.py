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
import re

# ===================== 설정값 (auto_cook.py와 동일) =====================
CELL1_CENTER = (2843, 67)  # 좌표 측정 당시 컴퓨터 기준. 다른 컴퓨터에서는
                            # 아래 창 추적으로 자동 보정됨 (창 크기가 같다면).
REF_ITEM = (2815, 0)       # 측정 당시 "아이템" 창의 (left, top)
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
SHIFT = 2               # (구) 좌표 미세 어긋남 보정 — 지금은 ALIGN이 대체
ALIGN = 7               # 아이콘을 상하좌우 ±이 픽셀까지 밀어보며 가장 잘맞는 위치를 찾음
MIN_ITEM_PX = 40        # 칸 중앙에 밝은 픽셀이 이보다 적으면 빈 칸으로 봄
# ======================================================================


def match_region(region, tpl):
    """region(=CELL_SIZE+2*ALIGN) 안에서 tpl을 1픽셀씩 밀어가며 최적 위치의 차이값."""
    import numpy as np
    tb = tpl[TOP_CUT:CELL_SIZE, :CELL_SIZE]
    tb_fg = tb.sum(axis=2) > 90
    hh, ww = tb.shape[:2]
    best = 1e9
    for oy in range(0, 2 * ALIGN + 1):
        for ox in range(0, 2 * ALIGN + 1):
            win = region[oy + TOP_CUT:oy + CELL_SIZE, ox:ox + CELL_SIZE]
            if win.shape[:2] != (hh, ww):
                continue
            fg = tb_fg | (win.sum(axis=2) > 90)
            if fg.sum() < 20:
                continue
            d = np.abs(win - tb)[fg].mean()
            if d < best:
                best = d
                if best < 4:
                    return best
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
            stem = os.path.splitext(fn)[0]
            base = re.sub(r"[_\-]?\d+$", "", stem) or stem   # 끝 숫자 제거해 그룹화
            img = np.array(Image.open(os.path.join(folder, fn)).convert("RGB"), dtype=int)
            templates.setdefault(base, []).append(img[:CELL_SIZE, :CELL_SIZE])

    if not templates:
        print("[문제] items 폴더에 등록된 재료 이미지가 없습니다.")
        print(f"       확인할 폴더: {folder}")
        return

    print("등록된 재료:", ", ".join(templates))
    print(f"인식 기준: 기본 {MATCH_THRESHOLD} 이하 (재료별 예외: {MATCH_THRESHOLDS})\n")

    global CELL1_CENTER
    try:
        import pygetwindow as gw
        w = next((w for w in gw.getAllWindows() if w.title == "아이템" and w.width > 0), None)
        if w:
            dx, dy = w.left - REF_ITEM[0], w.top - REF_ITEM[1]
            if dx or dy:
                CELL1_CENTER = (CELL1_CENTER[0] + dx, CELL1_CENTER[1] + dy)
                print(f"[창 추적] '아이템' 창 위치로 좌표 보정함 (dx={dx}, dy={dy})\n")
        else:
            print("[창 추적] '아이템' 창을 못 찾음 — 원래 좌표 그대로 사용\n")
    except ImportError:
        print("[창 추적] pygetwindow 없음 — 원래 좌표 그대로 사용 "
              "(pip install pygetwindow 하면 다른 컴퓨터에서도 자동 보정됨)\n")

    size = CELL_SIZE + 2 * ALIGN
    # 각 재료별 최소 차이값 추적
    best_for = {name: (1e9, None) for name in templates}

    with mss.mss() as sct:
        print("칸별 인식 결과 (행,열 → 인식결과 [차이값]):")
        for r in range(ROWS):
            line = []
            for c in range(COLS):
                nx = int(round(CELL1_CENTER[0] + c * PITCH_X))
                ny = int(round(CELL1_CENTER[1] + r * PITCH_Y))
                shot = sct.grab({"left": nx - size // 2, "top": ny - size // 2,
                                 "width": size, "height": size})
                region = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
                center = region[ALIGN + TOP_CUT:ALIGN + CELL_SIZE, ALIGN:ALIGN + CELL_SIZE]
                if int((center.sum(axis=2) > 90).sum()) < MIN_ITEM_PX:
                    line.append("[빈칸]")
                    continue
                bn, bd = None, 1e9
                for name, tpl_list in templates.items():
                    diff = min(match_region(region, tpl) for tpl in tpl_list)
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
