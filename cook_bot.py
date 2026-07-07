# -*- coding: utf-8 -*-
"""
음식만들기 자동 온도조절 봇 (꾹 누르기 방식)

- 온도계를 실시간 감시하면서 빨간(+)/파란(-) 손잡이를 "꾹 눌렀다 떼는" 방식으로 조절
- 연타하지 않음 (연타 시 게임 튕김 방지). 누른 상태에서 온도를 계속 보다가
  관성(떼도 잠깐 더 움직임)을 계산해서 미리 뗌
- F8 = 시작/정지 토글, F9 = 완전 종료
- 비상 정지: 마우스를 화면 왼쪽 위 구석으로 확 던지면 즉시 멈춤 (pyautogui failsafe)

사용 전: 게임 창을 좌표 측정했을 때와 똑같은 자리에 둘 것!
"""

import time
import random
import threading

import mss
import numpy as np
import pyautogui
import keyboard

# ===================== 설정값 (measure.py로 측정해서 수정) =====================

# 온도계 관(수은이 움직이는 세로 관) 영역 — 화면 절대 좌표
GAUGE_LEFT   = 3120   # 관 왼쪽 x
GAUGE_TOP    = 133    # 관 맨 위 y
GAUGE_WIDTH  = 20     # 관 가로 폭
GAUGE_HEIGHT = 85     # 관 세로 높이 (맨위 133 ~ 맨아래 218)

# 손잡이(버튼) 중심 좌표
PLUS_BTN  = (3253, 284)   # 빨간 + (온도 올리기)
MINUS_BTN = (3330, 285)   # 파란 - (온도 내리기)
BTN_JITTER = 9            # 클릭 위치 흔들림 반경(픽셀) — 버튼 반지름(13~14)보다 작게

# 게임의 "시작" 버튼 중심 좌표 — measure.py로 측정한 값
# None으로 바꾸면 시작 버튼을 누르지 않음 (직접 시작해야 함)
START_BTN = (3219, 389)

# 색상 (측정값)
YELLOW_RGB = (239, 231, 107)   # 적정 구간 안의 수은(노란색)
RED_RGB    = (189, 44, 33)     # 구간 밖의 수은(빨간색)
COLOR_TOL  = 50                # 색 허용 오차
MIN_PIXELS = 3                 # 한 줄에서 이 개수 이상 색이 잡혀야 수은으로 인정

# 적정 구간(눈금 두 선)의 위치 — 관 맨위=0.0, 맨아래=1.0 기준
# (영상 분석 결과: 위 선 0.42, 아래 선 0.54)
ZONE_TOP = 0.42
ZONE_BOT = 0.54

# 관성 보정 — 버튼을 떼도 온도가 이만큼(관 높이 비율) 더 움직인다고 보고 미리 뗌
# (영상 분석: 가열 관성 ≈ 관의 6~7%, 냉각 관성은 그 절반 이하)
MOMENTUM_UP   = 0.06   # + 누르다 뗄 때 추가로 더 올라가는 양
MOMENTUM_DOWN = 0.03   # - 누르다 뗄 때 추가로 더 내려가는 양

DEADBAND   = 0.015     # 구간 경계에서 이만큼은 봐줌 (경계에서 파르르 떨지 않게)
MAX_HOLD   = 1.6       # 한 번에 최대로 꾹 누르는 시간(초) — 넘으면 일단 떼고 다시 판단
MIN_GAP    = (0.28, 0.65)  # 뗀 뒤 다음 누름까지 최소 쉬는 시간 범위(초) — 연타 방지
SAMPLE_DT  = 0.03      # 온도 확인 주기(초)

# ==============================================================================

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

running = False
alive = True
need_start = False   # F8로 켤 때 시작 버튼을 한 번 눌러야 하는 상태

ZONE_CENTER = (ZONE_TOP + ZONE_BOT) / 2

_yellow = np.array(YELLOW_RGB, dtype=int)
_red = np.array(RED_RGB, dtype=int)


def read_pos(sct):
    """온도계 수은 꼭대기 위치를 0.0(맨위)~1.0(맨아래)으로 반환. 수은 없으면 None."""
    region = {"top": GAUGE_TOP, "left": GAUGE_LEFT,
              "width": GAUGE_WIDTH, "height": GAUGE_HEIGHT}
    img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]  # BGRA→RGB
    yellow = np.all(np.abs(img - _yellow) <= COLOR_TOL, axis=-1)
    red = np.all(np.abs(img - _red) <= COLOR_TOL, axis=-1)
    filled = (yellow.sum(axis=1) + red.sum(axis=1)) >= MIN_PIXELS
    rows = np.flatnonzero(filled)
    if rows.size == 0:
        return None
    return rows[0] / GAUGE_HEIGHT


def jittered(center):
    cx, cy = center
    return (cx + random.randint(-BTN_JITTER, BTN_JITTER),
            cy + random.randint(-BTN_JITTER, BTN_JITTER))


def hold_button(sct, button, release_when, label):
    """버튼을 꾹 누른 채 온도를 감시하다가 release_when(pos)이 참이 되면 뗌."""
    x, y = jittered(button)
    pyautogui.moveTo(x, y, duration=random.uniform(0.16, 0.3))  # +/- 간 이동을 살짝 더 느긋하게
    pyautogui.mouseDown()
    t0 = time.time()
    max_hold = MAX_HOLD * random.uniform(0.8, 1.0)
    try:
        while running and alive:
            if time.time() - t0 >= max_hold:
                break
            pos = read_pos(sct)
            if pos is not None and release_when(pos):
                break
            time.sleep(SAMPLE_DT)
    finally:
        pyautogui.mouseUp()
    held = time.time() - t0
    print(f"  {label} {held:.2f}초 꾹 누름", " " * 20)
    # 사람스러운 쉬는 텀 + 연타 방지
    time.sleep(random.uniform(*MIN_GAP))


def click_start():
    """게임의 시작 버튼을 사람처럼 한 번 클릭."""
    if START_BTN is None:
        print("\n[알림] START_BTN 미설정 → 시작 버튼 클릭 생략. 게임에서 직접 시작하세요.")
        return
    x = START_BTN[0] + random.randint(-12, 12)   # 시작 버튼은 가로로 긴 사각형
    y = START_BTN[1] + random.randint(-4, 4)
    pyautogui.moveTo(x, y, duration=random.uniform(0.08, 0.2))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.06, 0.14))
    pyautogui.mouseUp()
    print("\n시작 버튼 클릭!")
    time.sleep(random.uniform(0.5, 0.9))   # 게임이 반응할 시간


def worker():
    global running, alive
    try:
        _worker_loop()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        alive = False


def _worker_loop():
    global running, alive, need_start
    with mss.mss() as sct:
        while alive:
            if not running:
                time.sleep(0.1)
                continue

            if need_start:
                need_start = False
                click_start()
                continue

            pos = read_pos(sct)

            if pos is None:
                # 수은이 아예 안 보임 = 완전 차가움 → 불 올리기
                print("수은 없음 → + 가열", " " * 20, end="\r")
                hold_button(sct, PLUS_BTN,
                            lambda p: p - MOMENTUM_UP <= ZONE_CENTER, "+")
            elif pos > ZONE_BOT + DEADBAND:
                # 구간보다 아래(차가움) → + 를 꾹, 관성 감안해 미리 뗌
                print(f"위치 {pos:.2f} 낮음 → + 가열", " " * 12, end="\r")
                hold_button(sct, PLUS_BTN,
                            lambda p: p - MOMENTUM_UP <= ZONE_CENTER, "+")
            elif pos < ZONE_TOP - DEADBAND:
                # 구간보다 위(뜨거움) → - 를 꾹, 관성 감안해 미리 뗌
                print(f"위치 {pos:.2f} 높음 → - 냉각", " " * 12, end="\r")
                hold_button(sct, MINUS_BTN,
                            lambda p: p + MOMENTUM_DOWN >= ZONE_CENTER, "-")
            else:
                # 적정 구간 안 → 그냥 둠
                print(f"위치 {pos:.2f} 적정 (유지)", " " * 12, end="\r")
                # 아주 가끔 사람처럼 잠깐 멍때리기
                if random.random() < 0.02:
                    time.sleep(random.uniform(0.4, 1.0))
                else:
                    time.sleep(random.uniform(0.06, 0.15))


def toggle():
    global running, need_start
    running = not running
    if running:
        need_start = True   # 켤 때마다 게임의 시작 버튼부터 한 번 클릭
        print("\n▶ 시작됨")
    else:
        print("\n⏸ 정지됨")


def quit_all():
    global alive, running
    running = False
    alive = False
    print("\n종료합니다...")


def main():
    print("=" * 44)
    print(" 음식만들기 자동 온도조절 (꾹 누르기 방식)")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 44)
    keyboard.add_hotkey("f8", toggle)
    keyboard.add_hotkey("f9", quit_all)
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while alive:
        time.sleep(0.2)
    print("끝.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        input("\n엔터를 누르면 창이 닫힙니다...")
