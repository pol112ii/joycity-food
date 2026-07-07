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

# ----- 속도 예측 + 꾹누르기 제어 파라미터 (영상 분석 기반) -----
# 게임 특성: 버튼을 어느 정도 "꾹" 눌러야 온도가 움직이고, 떼도 관성으로 좀 더 감.
# 그래서 위치만 보고 목표에서 떼면 관성으로 지나쳐 진동함.
# → 누르는 동안 이동 "속도"로 앞을 예측(pred)해서, 목표에 닿기 전에 미리 뗌.
#   뗀 뒤엔 잠시 기다리며 관성이 멈추길 지켜보고, 필요하면 반대쪽을 다시 꾹.
LOOKAHEAD    = 1.1      # 속도로 이 초만큼 앞을 예측 (크게=더 일찍 뗌, 작게=늦게 뗌)
CTRL_DEADBAND = 0.04    # 위치가 목표 중심에서 이 안이면 적정으로 보고 안 누름
HOLD_MIN     = 0.18     # 한 번 누르면 최소 이만큼은 꾹 (톡 누름 방지)
HOLD_MAX     = 1.2      # 한 번에 최대 이만큼까지만 꾹 (넘으면 일단 떼고 재판단)
HOLD_GAP     = (0.35, 0.75)  # 뗀 뒤 관성 지켜보며 기다리는 시간(초)
STALL_V      = 0.04     # 이 속도(/초)보다 느리면 '멈춘 것'으로 봄
VEL_WINDOW   = 0.22     # 속도를 이 초 구간의 위치 변화로 계산 (노이즈 완화)
SAMPLE_DT  = 0.03
DONE_NONE_SEC = 1.2     # 창이 닫힌 채 수은이 이만큼 안 보이면 요리 끝으로 판단
MIN_ROUND_SEC = 6.0     # 시작 후 이 시간 전엔 '요리 끝'으로 판단 안 함 (오검출 방지)

# (구 방식 파라미터 — 지금은 안 씀, 참고용)
MOMENTUM_UP   = 0.06
MOMENTUM_DOWN = 0.03
DEADBAND   = 0.03

# ===================== 인벤토리 / 슬롯 (measure.py로 측정!) =====================
CELL1_CENTER = (2843, 67)  # 인벤토리 첫 칸(왼쪽 위) 중심 좌표
# 간격은 1번칸과 6번칸(멀리 떨어진 칸) 좌표로 계산해서 오차를 최소화함
PITCH_X = 41.6          # 옆 칸까지 가로 간격
PITCH_Y = 41.25         # 아래 칸까지 세로 간격
COLS = 6
ROWS = 5
CELL_SIZE = 32          # capture_items.py와 같은 값
SEARCH_MARGIN = 4       # 계산된 칸 위치가 어긋나도 실제 아이콘 중심을 스스로 찾는 여유 범위
                        # (칸 간격 41px보다 너무 넓으면 옆 칸까지 침범해서 오작동하니 좁게)

SLOT1_CENTER = (3155, 87)  # 요리창 재료 슬롯 1번(맨 왼쪽 검은 칸) 중심
SLOT_PITCH_X = 50       # 슬롯 간 가로 간격
NUM_SLOTS = 4           # 지금 열려있는 슬롯 수 (5개 열리면 5로)

# ===================== 레시피 =====================
# (재료이름, 넣을 개수) — 이름은 items 폴더의 파일명과 똑같이.
# 개수만큼 드래그함 (슬롯 1번부터 차례로). 합계는 슬롯 수(5) 이하로.
RECIPE = [
    ("버섯", 1),
    ("쌀", 1),
    ("최상급향신료", 2),
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
MATCH_THRESHOLD = 22    # 기본 인식 기준 (차이값) — 오인식하면 낮추기
# 재료별로 다른 기준. 버섯은 수량(1개/3개/5개)에 따라 아이콘 렌더링이
# 살짝 달라서 차이값이 34~39까지 나올 때가 있어 넉넉하게 잡음.
# 반면 향신료는 비슷한 분홍 아이템이 많아 기준을 좁게 유지해야 오인식 안 함.
MATCH_THRESHOLDS = {
    "버섯": 45,
}


def threshold_for(name):
    return MATCH_THRESHOLDS.get(name, MATCH_THRESHOLD)
TOP_CUT = 13            # 칸 위쪽 수량 숫자 영역을 가림 (이 픽셀만큼 위 무시)
SHIFT = 2               # 좌표 미세 어긋남 보정 (±픽셀)
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


def smooth_move_to(x, y, duration, bow=0):
    """마우스를 여러 중간 지점을 거쳐 부드럽게 이동 (순간이동처럼 안 보이게).

    pyautogui의 duration 옵션만으로는 중간 지점이 너무 성겨서 실제로는
    툭툭 끊겨 이동하는 것처럼 보일 수 있어서, 직접 지점을 잘게 쪼개고
    가속→감속(ease) 곡선 + 살짝 휘어진 경로(bow)로 이동시킴.
    """
    sx, sy = pyautogui.position()
    dist = max(abs(x - sx), abs(y - sy), 1)
    steps = min(max(int(duration / 0.012), 10), 80)
    # 이동 방향에 수직인 방향으로 살짝 휘어지게 (사람 손 궤적 흉내)
    perp_x, perp_y = -(y - sy), (x - sx)
    plen = max((perp_x ** 2 + perp_y ** 2) ** 0.5, 1)
    perp_x, perp_y = perp_x / plen, perp_y / plen
    bow_amount = random.uniform(-bow, bow) if bow else 0
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)          # ease-in-out (천천히 시작 → 빨라짐 → 천천히 도착)
        bow_factor = 4 * e * (1 - e)     # 중간 지점에서 최대로 휘고 양끝에서는 0
        ix = sx + (x - sx) * e + perp_x * bow_amount * bow_factor
        iy = sy + (y - sy) * e + perp_y * bow_amount * bow_factor
        pyautogui.moveTo(int(round(ix)), int(round(iy)))
        time.sleep(duration / steps)


def hold_button(sct, button, release_when, label):
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
    print(f"  {label} {time.time()-t0:.2f}초 꾹 누름", " " * 20)
    time.sleep(random.uniform(*MIN_GAP))


def hold_toward(sct, button, sign, label):
    """버튼을 꾹 누르되, 속도로 예측한 위치가 목표 중심에 닿으면 미리 뗌.

    sign=+1: 가열(+, 수은 상승=pos 감소) → pred가 중심 이하로 내려오면 뗌
    sign=-1: 냉각(-, 수은 하강=pos 증가) → pred가 중심 이상으로 올라오면 뗌
    떼고 나선 HOLD_GAP만큼 관성 지켜보며 대기.
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


def idle_wander(loops=None):
    """요리 끝나고 다음 판 시작 전, 마우스를 의미 없이 잠깐 돌아다니게 함.

    매번 정확히 같은 자리로만 딱딱 움직이면 기계적으로 보이니, 사람이
    딴청 피우듯 근처를 몇 번 배회하다가 멈추게 함. 클릭은 안 함.
    """
    if loops is None:
        loops = random.randint(1, 3)
    x, y = pyautogui.position()
    for _ in range(loops):
        nx = x + random.randint(-100, 100)
        ny = y + random.randint(-70, 70)
        smooth_move_to(nx, ny, random.uniform(0.3, 0.7), bow=random.uniform(10, 30))
        time.sleep(random.uniform(0.15, 0.5))
        x, y = nx, ny


def human_click(point, jx=10, jy=4):
    x = point[0] + random.randint(-jx, jx)
    y = point[1] + random.randint(-jy, jy)
    smooth_move_to(x, y, random.uniform(0.25, 0.45), bow=8)
    time.sleep(random.uniform(0.1, 0.25))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.08, 0.18))
    pyautogui.mouseUp()


def human_drag(src, dst):
    """사람처럼 드래그: 누르고 → 이동(중간점 경유) → 떼기. 서두르지 않음(튕김 방지)."""
    sx, sy = jittered(src, 5)
    dx, dy = jittered(dst, 5)
    smooth_move_to(sx, sy, random.uniform(0.4, 0.7), bow=15)
    time.sleep(random.uniform(0.2, 0.35))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.2, 0.35))
    # 중간점 하나 거쳐서 자연스러운 곡선 흉내
    mx = (sx + dx) // 2 + random.randint(-25, 25)
    my = (sy + dy) // 2 + random.randint(-15, 15)
    smooth_move_to(mx, my, random.uniform(0.28, 0.5), bow=12)
    smooth_move_to(dx, dy, random.uniform(0.28, 0.5), bow=12)
    time.sleep(random.uniform(0.2, 0.35))
    pyautogui.mouseUp()
    # 다음 동작까지 사람처럼 한 템포 쉬기 (드래그 연속 튕김 방지의 핵심)
    time.sleep(random.uniform(1.0, 1.9))


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
        templates[name] = img[:CELL_SIZE, :CELL_SIZE]   # 전체 저장, 비교 때 위쪽만 가림
    return templates


def match_diff(cell, tpl):
    """cell(32x32)과 tpl(32x32)의 차이값.

    위쪽 숫자영역 제외 + ±SHIFT 흔들림 보정 + "검은 배경이 아닌 부분(그림이
    있는 부분)"만 골라서 비교. 칸 대부분이 검은 배경이라 배경끼리는 항상
    똑같이 맞아떨어지는데, 그걸 그대로 평균에 넣으면 진짜 그림 차이가
    희석돼서 완전히 다른 아이템끼리도 비슷한 점수가 나오는 문제가 있었음.
    """
    m = SHIFT
    H, W = cell.shape[:2]
    base = cell[TOP_CUT + m:H - m, m:W - m]
    best = 1e9
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            comp = tpl[TOP_CUT + m + dy:H - m + dy, m + dx:W - m + dx]
            if comp.shape != base.shape:
                continue
            fg = (base.sum(axis=2) > 90) | (comp.sum(axis=2) > 90)
            if fg.sum() < 20:
                continue   # 둘 다 거의 빈 배경이면 비교 의미 없음 → 건너뜀
            d = np.abs(base[fg] - comp[fg]).mean()
            if d < best:
                best = d
    return best


def locate_true_center(sct, nominal_cx, nominal_cy):
    """계산된 칸 중심 근처를 넓게 캡처해서 실제 아이콘(밝은 픽셀)의 중심을 찾음."""
    m = SEARCH_MARGIN
    size = CELL_SIZE + 2 * m
    nx, ny = int(round(nominal_cx)), int(round(nominal_cy))
    shot = sct.grab({"left": nx - size // 2, "top": ny - size // 2,
                      "width": size, "height": size})
    img = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
    bright = img.sum(axis=2) > 90
    ys, xs = np.nonzero(bright)
    if len(ys) < 20:
        return nominal_cx, nominal_cy, False
    true_cx = nx - size // 2 + int(xs.mean())
    true_cy = ny - size // 2 + int(ys.mean())
    return true_cx, true_cy, True


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
            nominal_cx = CELL1_CENTER[0] + c * PITCH_X
            nominal_cy = CELL1_CENTER[1] + r * PITCH_Y
            cx, cy, has_item = locate_true_center(sct, nominal_cx, nominal_cy)
            if not has_item:
                continue
            shot = sct.grab({"left": cx - half, "top": cy - half,
                             "width": CELL_SIZE, "height": CELL_SIZE})
            cell = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
            best_name, best_diff = None, 1e9
            for name, tpl in templates.items():
                diff = match_diff(cell, tpl)
                min_diffs[name] = min(min_diffs[name], diff)
                if diff < best_diff:
                    best_name, best_diff = name, diff
            if best_name is not None and best_diff <= threshold_for(best_name):
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
        time.sleep(random.uniform(1.2, 2.0))
    print("직업활동 버튼 클릭")
    human_click(JOB_ACT_BTN, jx=8, jy=4)
    t0 = time.time()
    while running and alive and time.time() - t0 < REOPEN_WAIT:
        if window_open(sct):
            print("음식만들기 창 열림 확인")
            time.sleep(random.uniform(1.0, 1.8))
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
            # 가끔 화면 캡처 타이밍이 안 좋아 한 번 실패할 수 있어 최대 3번 재시도
            found, min_diffs = {}, {}
            for attempt in range(3):
                found, min_diffs = scan_inventory(sct, templates)
                if name in found:
                    break
                time.sleep(random.uniform(0.2, 0.4))
            if slot == 0:
                print("인벤토리 인식:", {k: len(v) for k, v in found.items()})
            if name not in found:
                print(f"[중단] 재료 '{name}' 를 인벤토리에서 못 찾음 (3번 재시도함)")
                print(f"       가장 비슷한 칸의 차이값: {min_diffs.get(name, 0):.1f} "
                      f"(인식 기준: {threshold_for(name)} 이하)")
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
    """시작 클릭 → 속도예측 꾹누르기로 온도 유지 → 요리 종료 감지. 정상 종료면 True.

    제어 원리:
      온도계는 버튼을 어느 정도 꾹 눌러야 움직이고 떼도 관성으로 더 가는 시스템.
      그래서 누르는 동안 이동 '속도'로 앞을 예측(pred)해서 목표에 닿기 전에 미리 떼고,
      뗀 뒤엔 잠시 지켜보다가 필요하면 반대쪽을 꾹. (한 방향 연속 X)
      '요리 끝'은 수은이 안 보이는 것만으로 판단하지 않고, 음식만들기 창이 실제로
      닫혔는지(초록 배경 사라짐)로 판단해 오검출을 막음.
    """
    print("시작 버튼 클릭!")
    human_click(START_BTN, jx=12, jy=4)
    time.sleep(random.uniform(0.8, 1.4))

    t_start = time.time()
    seen = False           # 수은을 한 번이라도 봤는지
    none_since = None      # 창 닫힌 채 수은이 안 보이기 시작한 시각
    last_pos = 0.9         # 마지막으로 본 위치 (수은 사라졌을 때 어느 쪽인지 추정용)
    last_off = 0.0         # 눈금 밖 보정용 마지막 누름 시각

    while running and alive:
        now = time.time()
        if now - t_start > COOK_TIMEOUT:
            print("\n[경고] 시간 초과 — 이번 판 종료 처리")
            return False
        pos = read_pos(sct)

        if pos is None:
            window = window_open(sct)
            if seen and not window and now - t_start > MIN_ROUND_SEC:
                # 창이 실제로 닫힘 = 요리 끝
                none_since = none_since or now
                if now - none_since > DONE_NONE_SEC:
                    print("\n요리 끝 감지!")
                    return True
                time.sleep(SAMPLE_DT)
                continue
            # 창은 열려있는데 수은이 눈금 밖 = 너무 차갑거나 뜨거움 → 되돌리기
            none_since = None
            if now - last_off > 0.5:
                if last_pos >= ZONE_CENTER:   # 마지막이 아래(차가움)였으면 가열
                    hold_toward(sct, PLUS_BTN, +1, "+")
                else:                          # 위(뜨거움)였으면 냉각
                    hold_toward(sct, MINUS_BTN, -1, "-")
                last_off = time.time()
            else:
                time.sleep(SAMPLE_DT)
            continue

        seen = True
        none_since = None
        last_pos = pos

        # 목표 중심 기준: pos > 중심 = 너무 차가움(아래) / pos < 중심 = 너무 뜨거움(위)
        if pos > ZONE_CENTER + CTRL_DEADBAND:
            print(f"pos {pos:.2f} 낮음(차가움) → + 가열", " " * 8, end="\r")
            hold_toward(sct, PLUS_BTN, +1, "+")
        elif pos < ZONE_CENTER - CTRL_DEADBAND:
            print(f"pos {pos:.2f} 높음(뜨거움) → - 냉각", " " * 8, end="\r")
            hold_toward(sct, MINUS_BTN, -1, "-")
        else:
            print(f"pos {pos:.2f} 적정 (유지)", " " * 12, end="\r")
            time.sleep(random.uniform(0.08, 0.18))
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
                    # 판 사이 휴식 — 마우스를 잠깐 배회시킨 뒤 쉼
                    idle_wander()
                    time.sleep(random.uniform(1.0, 2.0))
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
