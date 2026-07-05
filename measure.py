# -*- coding: utf-8 -*-
"""
좌표/색상 측정 도구.

실행하고 게임 창 위의 원하는 지점에 마우스를 올려두면
그 지점의 화면 좌표와 RGB 색상이 실시간으로 출력됨.
멀티모니터 환경(좌표가 3000 넘는 화면)도 지원.

종료: Ctrl+C
"""

import time

try:
    import mss
    import pyautogui

    print("측정 시작! 게임 창을 띄우고, 원하는 위치에 마우스를 올려두세요.")
    print("끝내려면 이 창에서 Ctrl+C\n")

    with mss.mss() as sct:
        while True:
            x, y = pyautogui.position()
            pixel = sct.grab({"top": y, "left": x, "width": 1, "height": 1}).pixel(0, 0)
            print(f"좌표: ({x}, {y})   색상(RGB): {pixel}          ", end="\r")
            time.sleep(0.25)
except KeyboardInterrupt:
    print("\n\n측정 종료됨.")
except Exception:
    import traceback
    print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
    traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
