# -*- coding: utf-8 -*-
"""
진단 도구 — 클릭은 하지 않고, 봇이 온도계를 어떻게 보고 있는지만 실시간 출력.

이 파일 하나만 있으면 실행됨 (다른 파일 필요 없음).
설정값은 cook_bot.py와 똑같이 맞춰져 있음. cook_bot.py에서 좌표를 바꿨다면
여기도 같이 바꿀 것.

종료: Ctrl+C 또는 창 닫기
"""

import time

# ===================== 설정값 (cook_bot.py와 동일하게) =====================
GAUGE_LEFT   = 3120   # 온도계 관 왼쪽 x
GAUGE_TOP    = 133    # 관 맨 위 y
GAUGE_WIDTH  = 20     # 관 가로 폭
GAUGE_HEIGHT = 85     # 관 세로 높이

YELLOW_RGB = (239, 231, 107)
RED_RGB    = (189, 44, 33)
COLOR_TOL  = 50
MIN_PIXELS = 3

ZONE_TOP = 0.42
ZONE_BOT = 0.54
# ==========================================================================


def main():
    import mss
    import numpy as np

    yellow = np.array(YELLOW_RGB, dtype=int)
    red = np.array(RED_RGB, dtype=int)
    region = {"top": GAUGE_TOP, "left": GAUGE_LEFT,
              "width": GAUGE_WIDTH, "height": GAUGE_HEIGHT}

    print("진단 시작. 게임을 직접 플레이하면서 아래 숫자를 관찰하세요. Ctrl+C로 종료.")
    print(f"적정 구간: {ZONE_TOP:.2f} ~ {ZONE_BOT:.2f}  (0=관 맨위, 1=관 맨아래)\n")

    with mss.mss() as sct:
        while True:
            img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]
            yel_mask = np.all(np.abs(img - yellow) <= COLOR_TOL, axis=-1)
            red_mask = np.all(np.abs(img - red) <= COLOR_TOL, axis=-1)
            filled = (yel_mask.sum(axis=1) + red_mask.sum(axis=1)) >= MIN_PIXELS
            rows = np.flatnonzero(filled)
            pos = rows[0] / GAUGE_HEIGHT if rows.size else None
            avg = tuple(img.reshape(-1, 3).mean(axis=0).astype(int))

            if pos is None:
                state = "수은 안 보임"
            elif pos > ZONE_BOT:
                state = "낮음(+필요)"
            elif pos < ZONE_TOP:
                state = "높음(-필요)"
            else:
                state = "적정"

            print(f"위치:{'-' if pos is None else format(pos, '.2f')}  "
                  f"노랑:{int(yel_mask.sum()):3d} 빨강:{int(red_mask.sum()):3d}  "
                  f"영역평균RGB:{avg}  → {state}      ", end="\r")
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n종료")
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        input("\n엔터를 누르면 창이 닫힙니다...")
