# -*- coding: utf-8 -*-
"""
아이템 아이콘 등록 도구.

인벤토리(아이템 창)의 각 칸을 캡처해서 items 폴더에 저장함.
실행 후 items 폴더를 열어서:
  1. 빈 칸/필요 없는 파일은 삭제
  2. 남은 파일 이름을 재료 이름으로 변경 (예: cell_1_1.png → 체리.png)
이름을 바꾼 파일이 auto_cook.py가 인식하는 "정답 이미지"가 됨.

같은 재료를 여러 장 등록하려면 이름 끝에 숫자만 붙이면 됨:
  버섯1.png, 버섯2.png, 버섯20.png → 전부 "버섯"으로 인식.
버섯처럼 수량(1개/3개/5개/20개...)에 따라 아이콘이 조금씩 다르게 보이는
재료는 이렇게 여러 수량의 칸을 각각 캡처해서 등록하면 인식이 훨씬 안정적임.

사용 전: 아래 설정값을 measure.py로 측정해서 채울 것.
"""

import os

# ===================== 설정값 (measure.py로 측정) =====================
CELL1_CENTER = (2843, 67)  # 인벤토리 첫 칸(왼쪽 위) 중심 좌표
# 간격은 1번칸과 6번칸(멀리 떨어진 칸) 좌표로 계산해서 오차를 최소화함:
#   PITCH_X = ([1,6]중심x - [1,1]중심x) / 5 = (3051-2843)/5
#   PITCH_Y = ([5,1]중심y - [1,1]중심y) / 4 = (232-67)/4
PITCH_X = 41.6          # 옆 칸 중심까지 가로 간격
PITCH_Y = 41.25         # 아래 칸 중심까지 세로 간격
COLS = 6                # 가로 칸 수
ROWS = 5                # 세로 줄 수
CELL_SIZE = 32          # 캡처할 정사각형 크기(픽셀) — 칸보다 살짝 작게
SEARCH_MARGIN = 4       # 계산된 칸 위치가 몇 픽셀 어긋나도 실제 아이콘 중심을
                        # 스스로 찾아 보정하는 여유 범위(픽셀) — 너무 넓으면 옆 칸까지 침범함
# =====================================================================


def locate_true_center(sct, nominal_cx, nominal_cy):
    """계산된 칸 중심 근처를 넓게 캡처해서 실제 아이콘(밝은 픽셀)의 중심을 찾음.

    반환: (진짜중심x, 진짜중심y, 아이템있음여부)
    """
    import numpy as np
    m = SEARCH_MARGIN
    size = CELL_SIZE + 2 * m
    nx, ny = int(round(nominal_cx)), int(round(nominal_cy))
    shot = sct.grab({"left": nx - size // 2, "top": ny - size // 2,
                      "width": size, "height": size})
    img = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
    bright = img.sum(axis=2) > 90   # 검은 배경보다 밝은 픽셀 = 아이콘/숫자뱃지
    ys, xs = np.nonzero(bright)
    if len(ys) < 20:
        return nominal_cx, nominal_cy, False
    true_cx = nx - size // 2 + int(xs.mean())
    true_cy = ny - size // 2 + int(ys.mean())
    return true_cx, true_cy, True


def main():
    import mss
    import numpy as np
    from PIL import Image

    if CELL1_CENTER == (0, 0):
        print("[설정 필요] CELL1_CENTER가 (0,0)입니다.")
        print("measure.py로 인벤토리 첫 칸 중심 좌표를 재서 이 파일 상단에 넣어주세요.")
        return

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items")
    os.makedirs(outdir, exist_ok=True)

    half = CELL_SIZE // 2
    saved = skipped = 0
    with mss.mss() as sct:
        for r in range(ROWS):
            for c in range(COLS):
                nominal_cx = CELL1_CENTER[0] + c * PITCH_X
                nominal_cy = CELL1_CENTER[1] + r * PITCH_Y
                cx, cy, has_item = locate_true_center(sct, nominal_cx, nominal_cy)
                if not has_item:
                    skipped += 1
                    continue
                shot = sct.grab({"left": cx - half, "top": cy - half,
                                 "width": CELL_SIZE, "height": CELL_SIZE})
                img = np.asarray(shot)[:, :, :3][:, :, ::-1]  # BGRA→RGB
                Image.fromarray(img.astype("uint8")).save(
                    os.path.join(outdir, f"cell_{r+1}_{c+1}.png"))
                saved += 1

    print(f"완료! {saved}개 저장, 빈 칸 {skipped}개 건너뜀")
    print(f"저장 위치: {outdir}")
    print("이제 items 폴더를 열어서 파일 이름을 재료 이름으로 바꿔주세요.")
    print("예: cell_1_1.png → 체리.png")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
