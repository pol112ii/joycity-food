# -*- coding: utf-8 -*-
"""
진단 도구 — 클릭은 하지 않고, 봇이 온도계를 어떻게 보고 있는지만 실시간 출력.

cook_bot.py와 같은 설정값을 그대로 읽어서 사용하므로,
봇이 이상하게 동작하면 먼저 이걸 돌려서 인식이 제대로 되는지 확인할 것.

종료: Ctrl+C
"""

import time

import mss
import numpy as np

from cook_bot import (GAUGE_LEFT, GAUGE_TOP, GAUGE_WIDTH, GAUGE_HEIGHT,
                      ZONE_TOP, ZONE_BOT, COLOR_TOL, MIN_PIXELS,
                      _yellow, _red, read_pos)

print("진단 시작. 게임을 플레이하면서 아래 숫자를 관찰하세요. Ctrl+C로 종료.")
print(f"적정 구간: {ZONE_TOP:.2f} ~ {ZONE_BOT:.2f}  (0=관 맨위, 1=관 맨아래)\n")

region = {"top": GAUGE_TOP, "left": GAUGE_LEFT,
          "width": GAUGE_WIDTH, "height": GAUGE_HEIGHT}

try:
    with mss.mss() as sct:
        while True:
            img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]
            yellow_n = int(np.all(np.abs(img - _yellow) <= COLOR_TOL, axis=-1).sum())
            red_n = int(np.all(np.abs(img - _red) <= COLOR_TOL, axis=-1).sum())
            pos = read_pos(sct)
            avg = tuple(img.reshape(-1, 3).mean(axis=0).astype(int))

            if pos is None:
                state = "수은 안 보임"
            elif pos > ZONE_BOT:
                state = "낮음(+필요)"
            elif pos < ZONE_TOP:
                state = "높음(-필요)"
            else:
                state = "적정"

            print(f"위치:{'-' if pos is None else f'{pos:.2f}'}  "
                  f"노랑:{yellow_n:3d} 빨강:{red_n:3d}  "
                  f"영역평균RGB:{avg}  → {state}      ", end="\r")
            time.sleep(0.2)
except KeyboardInterrupt:
    print("\n종료")
