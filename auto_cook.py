# -*- coding: utf-8 -*-
"""
음식만들기 풀 자동 봇.

F8 한 번이면:
  1. 인벤토리를 스캔해서 레시피 재료를 찾고
  2. 드래그해서 요리창 재료 슬롯에 넣고
  3. 시작 버튼을 클릭하고
  4. 온도를 적정 구간에 유지 (꾹 누르기 방식)
  5. 요리가 끝나면 (LOOP=True면 재료가 떨어질 때까지) 반복

이 파일 하나로 실행됨. 단, 같은 폴더에 items 폴더(아이콘 등록)가 있어야 함.
F8 = 시작/정지, F9 = 종료. 비상시: 마우스를 화면 왼쪽 위 구석으로.
"""

import os
import time
import random
import threading

import mss
import numpy as np
import pyautogui
import keyboard
from PIL import Image

# ===================== 온도계 / 버튼 (cook_bot.py와 동일) =====================
GAUGE_LEFT   = 3120
GAUGE_TOP    = 133
GAUGE_WIDTH  = 20
GAUGE_HEIGHT = 85

PLUS_BTN  = (3253, 284)
MINUS_BTN = (3330, 285)
BTN_JITTER = 9
START_BTN = (3219, 389)

YELLOW_RGB = (239, 231, 107)
RED_RGB    = (189, 44, 33)
COLOR_TOL  = 50
MIN_PIXELS = 3

ZONE_TOP = 0.42
ZONE_BOT = 0.54
MOMENTUM_UP   = 0.06
MOMENTUM_DOWN = 0.03
DEADBAND   = 0.015
MAX_HOLD   = 1.6
MIN_GAP    = (0.28, 0.65)
SAMPLE_DT  = 0.03

# ===================== 인벤토리 / 슬롯 (measure.py로 측정!) =====================
CELL1_CENTER = (2843, 67)  # 인벤토리 첫 칸(왼쪽 위) 중심 좌표
PITCH_X = 44            # 옆 칸까지 가로 간격
PITCH_Y = 39            # 아래 칸까지 세로 간격
COLS = 6
ROWS = 5
CELL_SIZE = 32          # capture_items.py와 같은 값

SLOT1_CENTER = (3155, 87)  # 요리창 재료 슬롯 1번(맨 왼쪽 검은 칸) 중심
SLOT_PITCH_X = 50       # 슬롯 간 가로 간격
NUM_SLOTS = 4           # 지금 열려있는 슬롯 수 (5개 열리면 5로)

# ===================== 레시피 =====================
# (재료이름, 넣을 개수) — 이름은 items 폴더의 파일명과 똑같이.
# 개수만큼 드래그함 (슬롯 1번부터 차례로). 합계는 슬롯 수(5) 이하로.
RECIPE = [
    ("체리", 1),
    # ("버섯", 1),
]

LOOP = True             # True면 재료가 떨어질 때까지 자동 반복 (False면 한 판만)

# ----- 요리창 다시 열기 (LOOP용) -----
# 요리가 끝나면 음식만들기 창이 닫히므로, 반복하려면 다시 여는 클릭이 필요.
# JOB_BTN     = 화면 아래 메뉴의 "직업" 아이콘 중심 좌표.
#               직업 창이 요리 중에도 계속 열려있다면 None으로 (클릭 생략).
# JOB_ACT_BTN = 직업 창의 "직업활동" 버튼 중심 좌표.
JOB_BTN     = (2509, 1186)   # 아래 메뉴바의 "직업" 아이콘
JOB_ACT_BTN = (2751, 245)    # 직업 창의 "직업활동" 버튼
GAUGE_BG_RGB = (40, 88, 47)   # 음식만들기 창의 온도계 주변 진초록 (열림 확인용)
REOPEN_WAIT = 8         # 창 열림 최대 대기(초)
MATCH_THRESHOLD = 28    # 아이콘 판별 기준 (평균 색 차이) — 오인식하면 낮추기
BADGE_CUT = 15          # 칸 왼쪽 위 수량 숫자를 피해서 비교 (이만큼 잘라냄)
                        # 두 자리 숫자(10~20)가 꽤 넓어서 넉넉히 잘라야 함
COOK_TIMEOUT = 90       # 요리 1판 최대 대기(초)
# ==============================================================================

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

running = False
alive = True

ZONE_CENTER = (ZONE_TOP + ZONE_BOT) / 2
_yellow = np.array(YELLOW_RGB, dtype=int)
_red = np.array(RED_RGB, dtype=int)


# ---------------------------------------------------------------- 온도계 읽기

def read_pos(sct):
    region = {"top": GAUGE_TOP, "left": GAUGE_LEFT,
              "width": GAUGE_WIDTH, "height": GAUGE_HEIGHT}
    img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]
    yellow = np.all(np.abs(img - _yellow) <= COLOR_TOL, axis=-1)
    red = np.all(np.abs(img - _red) <= COLOR_TOL, axis=-1)
    filled = (yellow.sum(axis=1) + red.sum(axis=1)) >= MIN_PIXELS
    rows = np.flatnonzero(filled)
    if rows.size == 0:
        return None
    return rows[0] / GAUGE_HEIGHT


# ---------------------------------------------------------------- 마우스 동작

def jittered(center, r=BTN_JITTER):
    return (center[0] + random.randint(-r, r),
            center[1] + random.randint(-r, r))


def hold_button(sct, button, release_when, label):
    x, y = jittered(button)
    pyautogui.moveTo(x, y, duration=random.uniform(0.04, 0.13))
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
    print(f"  {label} {time.time()-t0:.2f}초 꾹 누름", " " * 20)
    time.sleep(random.uniform(*MIN_GAP))


def human_click(point, jx=10, jy=4):
    x = point[0] + random.randint(-jx, jx)
    y = point[1] + random.randint(-jy, jy)
    pyautogui.moveTo(x, y, duration=random.uniform(0.08, 0.2))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.06, 0.14))
    pyautogui.mouseUp()


def human_drag(src, dst):
    """사람처럼 드래그: 누르고 → 이동(중간점 경유) → 떼기."""
    sx, sy = jittered(src, 5)
    dx, dy = jittered(dst, 5)
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.12, 0.3))
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.08, 0.2))
    # 중간점 하나 거쳐서 자연스러운 곡선 흉내
    mx = (sx + dx) // 2 + random.randint(-25, 25)
    my = (sy + dy) // 2 + random.randint(-15, 15)
    pyautogui.moveTo(mx, my, duration=random.uniform(0.1, 0.22))
    pyautogui.moveTo(dx, dy, duration=random.uniform(0.1, 0.22))
    time.sleep(random.uniform(0.06, 0.15))
    pyautogui.mouseUp()
    time.sleep(random.uniform(0.25, 0.55))


# ---------------------------------------------------------------- 아이템 인식

def load_templates():
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items")
    templates = {}
    if not os.path.isdir(folder):
        return templates
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".png") or fn.startswith("cell_"):
            continue
        name = os.path.splitext(fn)[0]
        img = np.array(Image.open(os.path.join(folder, fn)).convert("RGB"), dtype=int)
        templates[name] = img[BADGE_CUT:, BADGE_CUT:]   # 수량 숫자 부분 제외
    return templates


def scan_inventory(sct, templates):
    """인벤토리 전체를 스캔.

    반환: (found, min_diffs)
      found     = {재료이름: [칸 중심좌표, ...]}
      min_diffs = {재료이름: 전체 칸 중 가장 비슷했던 차이값}  ← 인식 실패 진단용
    """
    found = {}
    min_diffs = {name: 1e9 for name in templates}
    half = CELL_SIZE // 2
    for r in range(ROWS):
        for c in range(COLS):
            cx = CELL1_CENTER[0] + c * PITCH_X
            cy = CELL1_CENTER[1] + r * PITCH_Y
            shot = sct.grab({"left": cx - half, "top": cy - half,
                             "width": CELL_SIZE, "height": CELL_SIZE})
            cell = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
            cell = cell[BADGE_CUT:, BADGE_CUT:]
            best_name, best_diff = None, 1e9
            for name, tpl in templates.items():
                h = min(cell.shape[0], tpl.shape[0])
                w = min(cell.shape[1], tpl.shape[1])
                diff = np.abs(cell[:h, :w] - tpl[:h, :w]).mean()
                min_diffs[name] = min(min_diffs[name], diff)
                if diff < best_diff:
                    best_name, best_diff = name, diff
            if best_name is not None and best_diff <= MATCH_THRESHOLD:
                found.setdefault(best_name, []).append((cx, cy))
    return found, min_diffs


# ---------------------------------------------------------------- 단계별 동작

_bg = np.array(GAUGE_BG_RGB, dtype=int)


def window_open(sct):
    """음식만들기 창이 열려있는지 — 온도계 영역에 특유의 진초록이 충분히 보이는지로 판단."""
    region = {"top": GAUGE_TOP, "left": GAUGE_LEFT,
              "width": GAUGE_WIDTH, "height": GAUGE_HEIGHT}
    img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]
    near_bg = np.all(np.abs(img - _bg) <= 30, axis=-1)
    return near_bg.mean() > 0.25


def reopen_window(sct):
    """직업 → 직업활동 클릭으로 음식만들기 창을 다시 염. 성공하면 True."""
    if JOB_ACT_BTN is None:
        print("[설정 필요] JOB_ACT_BTN(직업활동 버튼 좌표)이 없어서 반복 불가")
        return False
    if JOB_BTN is not None:
        print("직업 버튼 클릭")
        human_click(JOB_BTN, jx=5, jy=5)
        time.sleep(random.uniform(0.7, 1.2))
    print("직업활동 버튼 클릭")
    human_click(JOB_ACT_BTN, jx=8, jy=4)
    t0 = time.time()
    while running and alive and time.time() - t0 < REOPEN_WAIT:
        if window_open(sct):
            print("음식만들기 창 열림 확인")
            time.sleep(random.uniform(0.5, 0.9))
            return True
        time.sleep(0.2)
    print("[실패] 음식만들기 창이 안 열림 — 좌표/창 위치 확인")
    return False


def fill_slots(sct, templates):
    """레시피대로 재료를 요리창 슬롯에 드래그. 성공하면 True."""
    slot = 0
    for name, count in RECIPE:
        for _ in range(count):
            if slot >= NUM_SLOTS:
                print(f"[중단] 열려있는 슬롯({NUM_SLOTS}개)을 넘음 — RECIPE 수량 확인")
                return False
            # 드래그할 때마다 다시 스캔 (재고가 줄어 칸이 바뀌어도 따라감)
            found, min_diffs = scan_inventory(sct, templates)
            if slot == 0:
                print("인벤토리 인식:", {k: len(v) for k, v in found.items()})
            if name not in found:
                print(f"[중단] 재료 '{name}' 를 인벤토리에서 못 찾음")
                print(f"       가장 비슷한 칸의 차이값: {min_diffs.get(name, 0):.1f} "
                      f"(인식 기준: {MATCH_THRESHOLD} 이하)")
                print("       → 재료가 진짜 없으면 정상. 재료가 있는데 이러면 이 숫자를 알려주세요.")
                return False
            src = found[name][0]
            dst = (SLOT1_CENTER[0] + slot * SLOT_PITCH_X, SLOT1_CENTER[1])
            print(f"'{name}' → 슬롯 {slot+1} 드래그")
            human_drag(src, dst)
            slot += 1
            if not (running and alive):
                return False
    return True


def cook_one_round(sct):
    """시작 클릭 → 온도 유지 → 요리 종료 감지. 정상 종료면 True."""
    print("시작 버튼 클릭!")
    human_click(START_BTN, jx=12, jy=4)
    time.sleep(random.uniform(0.5, 0.9))

    t_start = time.time()
    seen = False        # 수은을 한 번이라도 봤는지
    none_since = None   # 수은이 안 보이기 시작한 시각

    while running and alive:
        if time.time() - t_start > COOK_TIMEOUT:
            print("[경고] 시간 초과 — 이번 판 종료 처리")
            return False
        pos = read_pos(sct)

        if pos is None:
            if seen:
                none_since = none_since or time.time()
                if time.time() - none_since > 2.5:
                    print("요리 끝 감지!")
                    return True
                time.sleep(0.1)
            else:
                # 아직 요리 시작 전 (수은이 올라오기 전) → + 로 가열 시작
                hold_button(sct, PLUS_BTN,
                            lambda p: p - MOMENTUM_UP <= ZONE_CENTER, "+")
            continue

        seen = True
        none_since = None

        if pos > ZONE_BOT + DEADBAND:
            print(f"위치 {pos:.2f} 낮음 → + 가열", " " * 12, end="\r")
            hold_button(sct, PLUS_BTN,
                        lambda p: p - MOMENTUM_UP <= ZONE_CENTER, "+")
        elif pos < ZONE_TOP - DEADBAND:
            print(f"위치 {pos:.2f} 높음 → - 냉각", " " * 12, end="\r")
            hold_button(sct, MINUS_BTN,
                        lambda p: p + MOMENTUM_DOWN >= ZONE_CENTER, "-")
        else:
            print(f"위치 {pos:.2f} 적정 (유지)", " " * 12, end="\r")
            if random.random() < 0.02:
                time.sleep(random.uniform(0.4, 1.0))
            else:
                time.sleep(random.uniform(0.06, 0.15))
    return False


# ---------------------------------------------------------------- 메인 루프

def worker():
    global running, alive
    try:
        templates = load_templates()
        if not templates:
            print("[주의] items 폴더에 등록된 아이콘이 없음 — capture_items.py부터 실행")
        else:
            print("등록된 재료:", ", ".join(templates))

        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.1)
                    continue

                if CELL1_CENTER == (0, 0) or SLOT1_CENTER == (0, 0):
                    print("[설정 필요] CELL1_CENTER / SLOT1_CENTER 좌표를 측정해서 넣어주세요.")
                    running = False
                    continue

                # 요리창이 닫혀있으면 (직업 → 직업활동으로) 다시 열기
                if not window_open(sct):
                    print("음식만들기 창이 닫혀있음 → 다시 열기")
                    if not reopen_window(sct):
                        running = False
                        continue

                if not fill_slots(sct, templates):
                    running = False
                    continue
                if not cook_one_round(sct):
                    running = False
                    continue

                print("★ 한 판 완료!")
                if not LOOP:
                    running = False
                    print("정지 (LOOP=False). 다시 하려면 F8.")
                else:
                    time.sleep(random.uniform(1.2, 2.5))
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        alive = False


def toggle():
    global running
    running = not running
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨")


def quit_all():
    global alive, running
    running = False
    alive = False
    print("\n종료합니다...")


def main():
    print("=" * 48)
    print(" 음식만들기 풀 자동 봇 (재료넣기 + 시작 + 온도조절)")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 48)
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
