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
PITCH_X = 44
PITCH_Y = 39
COLS = 6
ROWS = 5
CELL_SIZE = 32

MATCH_THRESHOLD = 22    # 이 값 이하면 '맞음' (새 비교 방식 기준)
TOP_CUT = 13            # 위쪽 수량숫자 영역을 가림 (이 픽셀 수만큼 위를 무시)
SHIFT = 2               # 좌표 미세 어긋남 보정 (±픽셀)
# ======================================================================


def match_diff(cell, tpl):
    """cell(32x32)과 tpl(32x32)의 차이값. 위쪽 숫자영역 제외 + ±SHIFT 흔들림 보정."""
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
            d = np.abs(base - comp).mean()
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
    print(f"인식 기준: 차이값 {MATCH_THRESHOLD} 이하면 '맞음'\n")

    half = CELL_SIZE // 2
    # 각 재료별 최소 차이값 추적
    best_for = {name: (1e9, None) for name in templates}

    with mss.mss() as sct:
        print("칸별 인식 결과 (행,열 → 인식결과 [차이값]):")
        for r in range(ROWS):
            line = []
            for c in range(COLS):
                cx = CELL1_CENTER[0] + c * PITCH_X
                cy = CELL1_CENTER[1] + r * PITCH_Y
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
                if bd <= MATCH_THRESHOLD:
                    line.append(f"{bn}({bd:.0f})")
                else:
                    line.append(f"?({bn}:{bd:.0f})")
            print(f" {r+1}행: " + "  ".join(line))

    print("\n재료별 '가장 잘 맞은 칸' 요약:")
    for name, (diff, where) in best_for.items():
        verdict = "인식 O" if diff <= MATCH_THRESHOLD else "인식 X (기준 초과)"
        print(f"  {name:12s} 최소차이 {diff:5.1f}  위치 {where}  → {verdict}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
