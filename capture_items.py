# -*- coding: utf-8 -*-
"""
아이템 아이콘 등록 도구.

인벤토리(아이템 창)의 각 칸을 캡처해서 items 폴더에 저장함.
실행 후 items 폴더를 열어서:
  1. 빈 칸/필요 없는 파일은 삭제
  2. 남은 파일 이름을 재료 이름으로 변경 (예: cell_1_1.png → 체리.png)
이름을 바꾼 파일이 auto_cook.py가 인식하는 "정답 이미지"가 됨.

사용 전: 아래 설정값을 measure.py로 측정해서 채울 것.
"""

import os

# ===================== 설정값 (measure.py로 측정) =====================
CELL1_CENTER = (0, 0)   # 인벤토리 첫 칸(왼쪽 위) 중심 좌표  ← 측정 필요!
PITCH_X = 36            # 옆 칸 중심까지 가로 간격 (둘째 칸 중심 x - 첫 칸 중심 x)
PITCH_Y = 36            # 아래 칸 중심까지 세로 간격
COLS = 7                # 가로 칸 수
ROWS = 5                # 세로 줄 수
CELL_SIZE = 32          # 캡처할 정사각형 크기(픽셀) — 칸보다 살짝 작게
# =====================================================================


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
                cx = CELL1_CENTER[0] + c * PITCH_X
                cy = CELL1_CENTER[1] + r * PITCH_Y
                shot = sct.grab({"left": cx - half, "top": cy - half,
                                 "width": CELL_SIZE, "height": CELL_SIZE})
                img = np.asarray(shot)[:, :, :3][:, :, ::-1]  # BGRA→RGB
                if img.std() < 12:   # 거의 단색 = 빈 칸 → 저장 안 함
                    skipped += 1
                    continue
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
