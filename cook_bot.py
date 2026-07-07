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

# ----- 속도 예측 + 꾹누르기 제어 파라미터 (영상 분석 기반) -----
# 게임 특성: 버튼을 어느 정도 "꾹" 눌러야 온도가 움직이고, 떼도 관성으로 좀 더 감.
# → 누르는 동안 이동 "속도"로 앞을 예측(pred)해서, 목표에 닿기 전에 미리 뗌.
#   뗀 뒤엔 잠시 기다리며 관성이 멈추길 지켜보고, 필요하면 반대쪽을 다시 꾹.
LOOKAHEAD    = 0.7      # 속도로 이 초만큼 앞을 예측 (크게=더 일찍 뗌)
CTRL_DEADBAND = 0.04    # 위치가 목표 중심에서 이 안이면 적정으로 보고 안 누름
HOLD_MIN     = 0.3     # 한 번 누르면 최소 이만큼은 꾹 (짧은 뽀짝 누름 방지)
HOLD_MAX     = 1.4     # 한 번에 최대 이만큼까지만 꾹
HOLD_GAP     = (0.6, 1.1)    # 뗀 뒤 관성 지켜보며 기다리는 시간(초)
REPRESS_SEC  = 1.6      # 같은 방향을 다시 누르기까지 최소 간격 — 연속 누름 방지
VEL_WINDOW   = 0.22    # 속도를 이 초 구간의 위치 변화로 계산
SAMPLE_DT  = 0.03      # 온도 확인 주기(초)

# (구 방식 파라미터 — 지금은 안 씀, 참고용)
MOMENTUM_UP   = 0.06
MOMENTUM_DOWN = 0.03
DEADBAND   = 0.03
MIN_HOLD   = 0.15
MAX_HOLD   = 1.4
MIN_GAP    = (0.28, 0.65)

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


def smooth_move_to(x, y, duration, bow=0):
    """마우스를 여러 중간 지점을 거쳐 부드럽게 이동 (순간이동처럼 안 보이게).

    pyautogui의 duration 옵션만으로는 중간 지점이 너무 성겨서 실제로는
    툭툭 끊겨 이동하는 것처럼 보일 수 있어서, 직접 지점을 잘게 쪼개고
    가속→감속(ease) 곡선 + 살짝 휘어진 경로(bow)로 이동시킴.
    """
    sx, sy = pyautogui.position()
    perp_x, perp_y = -(y - sy), (x - sx)
    plen = max((perp_x ** 2 + perp_y ** 2) ** 0.5, 1)
    perp_x, perp_y = perp_x / plen, perp_y / plen
    bow_amount = random.uniform(-bow, bow) if bow else 0
    steps = min(max(int(duration / 0.012), 10), 80)
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)
        bow_factor = 4 * e * (1 - e)
        ix = sx + (x - sx) * e + perp_x * bow_amount * bow_factor
        iy = sy + (y - sy) * e + perp_y * bow_amount * bow_factor
        pyautogui.moveTo(int(round(ix)), int(round(iy)))
        time.sleep(duration / steps)


def hold_button(sct, button, release_when, label):
    """버튼을 꾹 누른 채 온도를 감시하다가 release_when(pos)이 참이 되면 뗌."""
    x, y = jittered(button)
    smooth_move_to(x, y, random.uniform(0.16, 0.3), bow=6)  # +/- 간 이동을 살짝 더 느긋하게
    pyautogui.mouseDown()
    t0 = time.time()
    max_hold = MAX_HOLD * random.uniform(0.8, 1.0)
    try:
        while running and alive:
            elapsed = time.time() - t0
            if elapsed >= max_hold:
                break
            if elapsed >= MIN_HOLD:   # 최소 시간 지나기 전엔 순간 터치처럼 바로 떼지 않음
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


def hold_toward(sct, button, sign, label):
    """버튼을 꾹 누르되, 속도로 예측한 위치가 목표 중심에 닿으면 미리 뗌.

    sign=+1: 가열(+, 수은 상승=pos 감소) → pred가 중심 이하로 내려오면 뗌
    sign=-1: 냉각(-, 수은 하강=pos 증가) → pred가 중심 이상으로 올라오면 뗌
    """
    x, y = jittered(button)
    smooth_move_to(x, y, random.uniform(0.14, 0.26), bow=6)
    pyautogui.mouseDown()
    t0 = time.time()
    hist = []
    try:
        while running and alive:
            el = time.time() - t0
            if el >= HOLD_MAX:
                break
            pos = read_pos(sct)
            now = time.time()
            if pos is not None:
                hist.append((now, pos))
                hist[:] = [(t, p) for (t, p) in hist if now - t <= VEL_WINDOW]
                v = (pos - hist[0][1]) / max(now - hist[0][0], 1e-3) if len(hist) >= 2 else 0.0
                pred = pos + LOOKAHEAD * v
                if el >= HOLD_MIN:
                    if sign > 0 and pred <= ZONE_CENTER:
                        break
                    if sign < 0 and pred >= ZONE_CENTER:
                        break
            time.sleep(SAMPLE_DT)
    finally:
        pyautogui.mouseUp()
    print(f"  {label} {time.time()-t0:.2f}초 꾹 누름", " " * 18)
    time.sleep(random.uniform(*HOLD_GAP))


def click_start():
    """게임의 시작 버튼을 사람처럼 한 번 클릭."""
    if START_BTN is None:
        print("\n[알림] START_BTN 미설정 → 시작 버튼 클릭 생략. 게임에서 직접 시작하세요.")
        return
    x = START_BTN[0] + random.randint(-12, 12)   # 시작 버튼은 가로로 긴 사각형
    y = START_BTN[1] + random.randint(-4, 4)
    smooth_move_to(x, y, random.uniform(0.2, 0.35), bow=8)
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
    """속도예측 꾹누르기 제어: 누르는 동안 속도로 앞을 예측해 목표에 닿기 전에
    미리 떼고, 잠시 지켜본 뒤 필요하면 반대쪽을 꾹. 위치만 보던 예전 방식이
    관성 때문에 늘 목표를 지나쳐 진동하던 문제를 해결."""
    global running, alive, need_start
    last_pos = 0.9     # 마지막으로 본 위치 (수은 사라졌을 때 방향 추정용)
    last_dir = None    # 직전에 누른 방향 — 연속 같은방향 누름 방지
    last_press = 0.0

    def do_hold(sign):
        nonlocal last_dir, last_press
        if sign > 0:
            hold_toward(sct, PLUS_BTN, +1, "+"); last_dir = "+"
        else:
            hold_toward(sct, MINUS_BTN, -1, "-"); last_dir = "-"
        last_press = time.time()

    with mss.mss() as sct:
        while alive:
            if not running:
                time.sleep(0.1)
                continue

            if need_start:
                need_start = False
                click_start()
                last_pos, last_dir, last_press = 0.9, None, 0.0
                continue

            now = time.time()
            pos = read_pos(sct)

            if pos is None:
                # 수은이 눈금 밖 = 너무 차갑거나 뜨거움 → 마지막 위치로 방향 추정해 되돌리기
                want = "+" if last_pos >= ZONE_CENTER else "-"
                if want != last_dir or now - last_press > REPRESS_SEC:
                    do_hold(+1 if want == "+" else -1)
                else:
                    time.sleep(SAMPLE_DT)
                continue

            last_pos = pos

            if pos > ZONE_CENTER + CTRL_DEADBAND:
                want = "+"
            elif pos < ZONE_CENTER - CTRL_DEADBAND:
                want = "-"
            else:
                print(f"pos {pos:.2f} 적정 (유지)", " " * 12, end="\r")
                last_dir = None
                time.sleep(random.uniform(0.08, 0.18))
                continue

            if want == last_dir and now - last_press < REPRESS_SEC:
                print(f"pos {pos:.2f} {want} 후 관성 대기중", " " * 8, end="\r")
                time.sleep(SAMPLE_DT)
                continue

            print(f"pos {pos:.2f} → {want} 꾹", " " * 12, end="\r")
            do_hold(+1 if want == "+" else -1)


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
