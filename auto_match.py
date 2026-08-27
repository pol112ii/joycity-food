# -*- coding: utf-8 -*-
"""
가구만들기(그림 맞추기) 풀 자동 봇.

F8 한 번이면:
  직업 → 직업활동 → 가구만들기 창 열기
  → 재료 우클릭으로 넣기 → 시작 버튼
  → 5x5 카드 짝맞추기 (기억하면서 진행, 폭탄 밟으면 기억 초기화)
  → 창이 닫히면 한 판 완료 → 다음 판 반복
재료가 떨어지면 멈춤.

F8 = 시작/정지, F9 = 종료. 비상시: 마우스를 화면 왼쪽 위 구석으로.

■ 처음 쓰기 전에
  1. 창 배치 후:  py arrange_windows.py 저장
  2. 인식 확인:   py match_test.py      (카드판이 제대로 읽히는지)
  3. 한 판만 시험: py match_once.py     (재료 넣고 시작 버튼 앞에서 실행)
  4. 재료 등록:   아래 RECIPE 를 이번 레시피에 맞게 고치고,
                  items 폴더에 그 재료 아이콘 png 가 있어야 함
                  (없으면 capture_items.py 로 캡처 → 이름 바꾸기)
"""

import os
import re
import time
import random
import threading

import numpy as np
import mss
import pyautogui
import keyboard
from PIL import Image

# ==================== 이 컴퓨터 좌표 (measure.py 로 잰 값) ====================

# ----- 카드판 (가구만들기 창) -----
CARD1_CENTER = (1651, 167)   # 1행1열 카드 중심
CARD_PITCH_X = 45.0          # 옆 칸까지 가로 간격
CARD_PITCH_Y = 45.25         # 아래 칸까지 세로 간격
GRID = 5                     # 5x5

# 가구만들기 창이 열려있는지 확인할 기준점 (창 안 고정 초록 배경)
WIN_POINT = (1588, 293)
WIN_RGB = (23, 59, 21)
WIN_TOL = 40

# ----- 재료 슬롯 / 시작 버튼 (가구만들기 창) -----
SLOT1_CENTER = (1604, 89)    # 재료 슬롯 1번(맨 왼쪽) 중심
SLOT_PITCH_X = 62            # 슬롯 간 가로 간격 (2번칸 1666 - 1번칸 1604, 실측)
NUM_SLOTS = 3                # 지금 열려있는 슬롯 수 (5칸까지 열리면 5로)
START_BTN = (1691, 496)      # 시작 버튼

# ----- 인벤토리 (아이템 창) -----
CELL1_CENTER = (1249, 83)    # 첫 칸(왼쪽 위) 중심
PITCH_X = 52.4               # 옆 칸까지 가로 간격  ((1511-1249)/5)
PITCH_Y = 52.5               # 아래 칸까지 세로 간격 ((293-83)/4)
COLS = 6
ROWS = 5

# ----- 창 열기 버튼 -----
JOB_BTN = (761, 1002)        # 아래 메뉴바의 "직업" 아이콘
JOB_ACT_BTN = (1132, 304)    # 직업 창의 "직업활동" 버튼

# ==================== 레시피 (판마다 바뀌면 여기만 고치면 됨) ====================
# ("재료이름", 개수) 형태. 재료이름은 items 폴더의 png 파일명과 같아야 함.
#   예) items/나무판자.png, items/나무판자2.png  →  이름은 "나무판자"
# 합계가 NUM_SLOTS 를 넘으면 안 됨.
#
# ※ 비워두면([]) 재료 넣기를 건너뛰고 바로 시작 버튼을 누름.
#   (재료가 이미 들어있는 상태에서 시험할 때 유용)
RECIPE = [
    # ("나무판자", 2),
    # ("못", 1),
]

LOOP = True              # True면 재료가 떨어질 때까지 자동 반복

# ==================== 동작 설정 ====================
ROUND_TIMEOUT = 120      # 한 판이 이 시간(초)을 넘기면 뭔가 잘못된 것으로 보고 중단
FLIP_WAIT = 1.0          # 카드를 클릭하고 뒤집힐 때까지 최대 대기(초)
SETTLE = 0.06            # 뒤집힌 뒤 그림이 안정될 때까지 살짝 대기

# 카드 그림 비교 기준. 실측: 같은 그림 0.3~1.2 / 다른 그림 35~200
# → 34면 둘 사이 한가운데라 여유가 큼. 오판이 보이면 20 정도로 낮출 것.
SAME_DIFF = 34

# 카드 상태 판정 (배경 원 색을 볼 고리 반지름). 원 반지름 약 17px
RING_IN, RING_OUT = 12, 16
IMG_R = 13               # 그림 비교에 쓸 정사각형 반쪽 크기 (26x26)
SURE = 0.50              # 이 비율 이상이어야 그 색으로 확신

# ----- 재료 인식 (auto_cook.py 와 같은 방식) -----
CELL_SIZE = 32           # capture_items.py 와 같은 값
MATCH_THRESHOLD = 50     # 재료 인식 기준(차이값). 오인식하면 낮추기
MATCH_THRESHOLDS = {}    # 재료별로 다르게 주려면: {"나무판자": 40}
TOP_CUT = 13             # 칸 위쪽 수량 숫자 영역은 비교에서 제외
ALIGN = 7                # 아이콘을 ±이 픽셀까지 밀어보며 최적 위치를 찾음
MIN_ITEM_PX = 40         # 칸 중앙 밝은 픽셀이 이보다 적으면 빈 칸
SLOT_CHECK = 14          # 슬롯 채움 검사 상자 크기(중앙만 봐야 배경이 안 섞임)
MIN_SLOT_PX = 10         # 슬롯 중앙에 밝은 픽셀이 이보다 적으면 빈 슬롯
SCAN_EVERY = 10          # 인벤토리 전체 스캔 주기(판). 넣기 직전 한 칸 확인이 있어 길어도 안전

BTN_JITTER = 9
AUTO_RESTART_SEC = 60    # 오류로 멈췄을 때 이 시간 뒤 자동 재시작

# ----- 마우스를 사람처럼 (여기 숫자만 만지면 됨) -----
MOUSE_SPEED = 1.3        # 클수록 느리게 움직임 (1.0=기본). 눈으로 보고 조정하세요.
                         # 올리면 더 사람같지만 판이 길어짐. 시뮬레이션 실측:
                         #   1.0 → 판당 32~39초 / 1.2 → 42~46초 / 1.3 → 44~49초
                         # 제한시간(50~60초)을 넘겨 실패하면 낮출 것.
THINK_CHANCE = 0.22      # 카드를 고르기 전에 잠깐 '어디 눌러볼까' 하고 멈추는 빈도
THINK_SEC = (0.25, 0.65) # 그때 멈추는 시간(초)
OVERSHOOT_CHANCE = 0.28  # 목표를 살짝 지나쳤다가 되돌아오는 빈도 (사람 손 특징)
BOW_RANGE = (9, 22)      # 이동 경로가 휘는 정도 (클수록 크게 휨)

# 판이 길어지면 제한시간에 쫓기므로 점점 빨라짐 (느긋함 < 완주가 우선).
# 앞부분은 사람처럼 느긋하게(클릭당 0.8초쯤), 뒤로 갈수록 빨라져서
# 폭탄을 여러 번 밟은 판도 제한시간(50~60초) 안에 끝나게 함.
RELAX_UNTIL = 20         # 이 시간(초)까지는 여유롭게
HURRY_AT = 36            # 이 시간이 되면 최대한 빠르게
HURRY_FLOOR = 0.30       # 최대로 서둘렀을 때의 속도 배율 (작을수록 빠름)

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

running = False
alive = True
_round_t0 = 0.0          # 이번 판을 시작한 시각 (서두름 판단용)
_hurry_on = False        # 판 진행 중일 때만 서두름 계산을 적용
_scan_cache = None
_rounds_since_scan = 0
_rounds_done = 0


def threshold_for(name):
    return MATCH_THRESHOLDS.get(name, MATCH_THRESHOLD)


# ==================== 마우스 (사람처럼 움직이기) ====================

def jittered(center, r=BTN_JITTER):
    return (center[0] + random.randint(-r, r),
            center[1] + random.randint(-r, r))


def smooth_move_to(x, y, duration, bow=0):
    """마우스를 여러 중간 지점을 거쳐 부드럽게 이동 (순간이동처럼 안 보이게).

    가속→감속 곡선 + 살짝 휘어진 경로로 사람 손 궤적을 흉내냄.
    """
    sx, sy = pyautogui.position()
    steps = min(max(int(duration / 0.012), 10), 80)
    perp_x, perp_y = -(y - sy), (x - sx)
    plen = max((perp_x ** 2 + perp_y ** 2) ** 0.5, 1)
    perp_x, perp_y = perp_x / plen, perp_y / plen
    # 휘는 양: 0에 가까우면 직선처럼 보이므로 최소 크기를 보장하고 방향만 랜덤
    bow_amount = random.uniform(bow * 0.45, bow) * random.choice((-1, 1)) if bow else 0
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)
        bf = 4 * e * (1 - e)
        ix = sx + (x - sx) * e + perp_x * bow_amount * bf
        iy = sy + (y - sy) * e + perp_y * bow_amount * bf
        pyautogui.moveTo(int(round(ix)), int(round(iy)))
        time.sleep(duration / steps)


def human_click(point, jx=10, jy=4):
    x = point[0] + random.randint(-jx, jx)
    y = point[1] + random.randint(-jy, jy)
    smooth_move_to(x, y, random.uniform(0.25, 0.45), bow=8)
    time.sleep(random.uniform(0.1, 0.25))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.08, 0.18))
    pyautogui.mouseUp()


def direct_click(point, label, jx=4, jy=4):
    """곡선 없이 직선으로 곧장 이동해서 클릭 (작고 확실한 버튼용)."""
    x = point[0] + random.randint(-jx, jx)
    y = point[1] + random.randint(-jy, jy)
    print(f"  {label} 클릭 → ({x}, {y})")
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.35))
    time.sleep(random.uniform(0.12, 0.2))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.1, 0.18))
    pyautogui.mouseUp()


def urgency():
    """1.0 = 여유롭게, 작을수록 서두름.

    판 시작 후 RELAX_UNTIL 초까지는 사람처럼 느긋하게 움직이고, 그 뒤로는
    제한시간(50~60초)에 쫓기므로 점점 빨라짐. 폭탄을 여러 번 밟아 판이
    길어져도 시간 안에 끝낼 수 있게 하는 안전장치.
    """
    if not _hurry_on:
        return 1.0
    el = time.time() - _round_t0
    if el <= RELAX_UNTIL:
        return 1.0
    span = max(1.0, HURRY_AT - RELAX_UNTIL)
    return max(HURRY_FLOOR, 1.0 - (1.0 - HURRY_FLOOR) * (el - RELAX_UNTIL) / span)


def move_like_human(x, y):
    """사람 손처럼 휘어서 이동. 가끔 목표를 살짝 지나쳤다가 되돌아옴."""
    u = urgency()
    sx, sy = pyautogui.position()
    dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
    dur = min(0.80, max(0.20, dist / 420.0)) * MOUSE_SPEED * u
    bow = random.uniform(*BOW_RANGE)
    if dist > 40 and random.random() < OVERSHOOT_CHANCE * u:
        ox = x + random.randint(-15, 15)
        oy = y + random.randint(-13, 13)
        smooth_move_to(ox, oy, dur * 0.82, bow=bow)
        time.sleep(random.uniform(0.04, 0.10) * u)      # 살짝 멈칫
        smooth_move_to(x, y, max(0.07, dur * 0.33), bow=bow * 0.3)
    else:
        smooth_move_to(x, y, dur, bow=bow)


def think_pause():
    """'어디 눌러볼까' 하고 잠깐 멈추는 흔적."""
    u = urgency()
    if random.random() < THINK_CHANCE * u:
        time.sleep(random.uniform(*THINK_SEC) * u)


def click_card(pos):
    """카드 한 장을 사람처럼 클릭."""
    x = pos[0] + random.randint(-9, 9)
    y = pos[1] + random.randint(-9, 9)
    move_like_human(x, y)
    time.sleep(random.uniform(0.05, 0.14) * urgency())   # 누르기 직전 짧은 멈칫
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.05, 0.11))
    pyautogui.mouseUp()


def right_click_item(pos):
    """인벤토리 칸을 우클릭해서 재료를 슬롯으로 보냄."""
    x, y = jittered(pos, 4)
    smooth_move_to(x, y, random.uniform(0.25, 0.45), bow=10)
    time.sleep(random.uniform(0.1, 0.2))
    pyautogui.mouseDown(button="right")
    time.sleep(random.uniform(0.05, 0.12))
    pyautogui.mouseUp(button="right")
    time.sleep(random.uniform(0.35, 0.6))


def park_mouse():
    """스캔 전에 마우스를 인벤토리 밖으로 치움 (커서가 아이콘 덮는 것 방지)."""
    px = int(CELL1_CENTER[0])
    py = int(CELL1_CENTER[1] + ROWS * PITCH_Y + 55)
    smooth_move_to(px, py, random.uniform(0.15, 0.3), bow=8)
    time.sleep(random.uniform(0.1, 0.2))


def park_off_board():
    """카드판을 읽기 전에 커서를 판 밖으로 치움 (커서가 카드를 가리는 것 방지).

    사람이 '한 발 물러나서 판을 훑어보는' 동작처럼 보이게 매번 조금씩 다른
    자리로 감.
    """
    # 지금 커서 위치에서 '바로 아래'로만 빠짐 — 판을 가로질러 멀리 가면
    # 시간만 잡아먹으므로, 카드판을 벗어나는 최소 거리만 이동함
    cx, _ = pyautogui.position()
    lo = int(CARD1_CENTER[0] - CARD_PITCH_X * 0.7)
    hi = int(CARD1_CENTER[0] + CARD_PITCH_X * (GRID - 0.3))
    x = min(hi, max(lo, cx + random.randint(-18, 18)))
    y = int(CARD1_CENTER[1] + (GRID - 1) * CARD_PITCH_Y + random.randint(30, 52))
    move_like_human(x, y)


# ==================== 화면 읽기 ====================

_yy, _xx = np.mgrid[-RING_OUT:RING_OUT + 1, -RING_OUT:RING_OUT + 1]
_dist = np.sqrt(_yy ** 2 + _xx ** 2)
RING = (_dist >= RING_IN) & (_dist <= RING_OUT)
BOARD_MARGIN = RING_OUT + 6


def card_center(r, c):
    return (int(round(CARD1_CENTER[0] + c * CARD_PITCH_X)),
            int(round(CARD1_CENTER[1] + r * CARD_PITCH_Y)))


def grab(sct, cx, cy, half):
    shot = sct.grab({"left": cx - half, "top": cy - half,
                     "width": half * 2 + 1, "height": half * 2 + 1})
    return np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]


def grab_board(sct):
    """카드판 전체를 한 번에 캡처 (25칸을 따로 찍는 것보다 훨씬 빠름)."""
    x0, y0 = card_center(0, 0)
    x1, y1 = card_center(GRID - 1, GRID - 1)
    left, top = x0 - BOARD_MARGIN, y0 - BOARD_MARGIN
    w = (x1 - x0) + BOARD_MARGIN * 2 + 1
    h = (y1 - y0) + BOARD_MARGIN * 2 + 1
    shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
    return np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1], left, top


def cell_of(board, left, top, r, c, half):
    cx, cy = card_center(r, c)
    x, y = cx - left, cy - top
    return board[y - half:y + half + 1, x - half:x + half + 1]


def classify(px):
    """카드 배경 원 색으로 상태 판정: ?=뒷면 O=열림 X=폭탄 .=판정실패"""
    R, G, B = px[:, 0], px[:, 1], px[:, 2]
    green = ((G > 110) & (G > R + 35) & (G > B + 35)).mean()
    blue = ((B > 115) & (B > R + 30) & (B > G + 5)).mean()
    orange = ((R > 170) & (G > 60) & (G < 150) & (B < 85) & (R > B + 110)).mean()
    best = max(green, blue, orange)
    if best < SURE:
        return "."
    return "?" if best == green else ("O" if best == blue else "X")


def read_board(sct):
    """판 전체를 읽어 (상태, 열린카드그림) 반환.

    상태: {(r,c): '?'|'O'|'X'|'.'}   그림: {(r,c): 이미지}  (열린 카드만)
    """
    board, left, top = grab_board(sct)
    states, images = {}, {}
    for r in range(GRID):
        for c in range(GRID):
            s = classify(cell_of(board, left, top, r, c, RING_OUT)[RING])
            states[(r, c)] = s
            if s == "O":
                images[(r, c)] = cell_of(board, left, top, r, c, IMG_R)
    return states, images


def window_open(sct):
    """가구만들기 창이 열려있는지 (기준점 색이 맞는지)."""
    px = grab(sct, WIN_POINT[0], WIN_POINT[1], 2).reshape(-1, 3)
    return bool(np.abs(px - np.array(WIN_RGB)).sum(axis=1).min() <= WIN_TOL)


def diff(a, b):
    """두 카드 그림의 차이값 (작을수록 같은 그림)."""
    if a.shape != b.shape:
        return 1e9
    return float(np.abs(a - b).mean())


# ==================== 짝맞추기 본체 ====================

def wait_flip(sct, pos, was):
    """클릭한 카드가 뒤집힐 때까지 기다림. (상태, 그림) 반환."""
    r, c = pos
    t0 = time.time()
    while time.time() - t0 < FLIP_WAIT:
        states, images = read_board(sct)
        if states[pos] in ("O", "X") and states[pos] != was:
            time.sleep(SETTLE)
            states, images = read_board(sct)
            return states, images
        if not window_open(sct):
            return states, images
        time.sleep(0.04)
    return read_board(sct)


def read_clean(sct):
    """커서를 카드판 밖으로 치운 뒤 읽음 — 그림 비교용으로는 반드시 이걸 써야 함.

    카드를 클릭한 직후에는 커서가 그 카드를 덮고 있어서, 그대로 캡처하면
    같은 그림인데도 차이값이 20~29 정도 커짐(실측). 판정 기준이 34이므로
    멀쩡한 짝의 절반 이상이 '다른 그림'으로 오판됨. 그래서 그림을 저장하기
    전에는 항상 커서를 치우고 다시 읽는다.
    """
    park_off_board()
    return read_board(sct)


def find_known_pair(memory, not_pair=()):
    """기억해둔 카드 중 같은 그림 두 장을 찾음. 이미 아닌 걸로 확인된 조합은 건너뜀."""
    ks = list(memory)
    best = None
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            if frozenset((a, b)) in not_pair:
                continue
            d = diff(memory[a], memory[b])
            if d <= SAME_DIFF and (best is None or d < best[0]):
                best = (d, a, b)
    return best


def find_match(img, memory, not_pair=(), me=None):
    """그림 하나와 같은 그림을 기억에서 찾음."""
    best = None
    for p, m in memory.items():
        if p == me or (me is not None and frozenset((me, p)) in not_pair):
            continue
        d = diff(img, m)
        if d <= SAME_DIFF and (best is None or d < best[0]):
            best = (d, p)
    return best


def pick_unknown(states, memory, exclude=()):
    """아직 안 본 뒷면 카드 중 하나를 고름 (커서에서 가까운 쪽 위주)."""
    cands = [p for p, s in states.items()
             if s == "?" and p not in memory and p not in exclude]
    if not cands:
        return None
    mx, my = pyautogui.position()
    cands.sort(key=lambda p: (card_center(*p)[0] - mx) ** 2
               + (card_center(*p)[1] - my) ** 2)
    return random.choice(cands[:3])          # 가까운 3개 중 무작위 (너무 기계적이지 않게)


def play_board(sct, verbose=True):
    """5x5 짝맞추기를 창이 닫힐 때까지 진행. (완료여부, 통계) 반환.

    핵심 규칙 (녹화 영상 분석으로 확인):
      - 짝이 맞으면 두 장 다 계속 열려있음
      - 틀리면 '다음 카드를 클릭하는 순간' 닫힘 (시간이 지나서가 아님)
        → 그래서 '한 턴의 첫 클릭 직후' 열려있는 카드 = 이미 맞춘 카드
          이 성질을 이용해 매 턴 게임에게 직접 정답을 확인함
      - 폭탄(주황)을 밟으면 못 맞춘 카드들의 자리가 전부 섞임 → 기억을 버림

    그림이 비슷해서 짝이라고 오판할 수 있으므로, 두 장을 눌러본 뒤 실제로
    맞았는지 게임 화면으로 확인하고, 아니었으면 그 조합을 기억해서 다시
    시도하지 않음(not_pair). 이게 없으면 같은 카드를 무한히 다시 열게 됨.
    """
    global _round_t0, _hurry_on
    memory = {}          # {(r,c): 그림}  열어봤지만 아직 못 맞춘 카드
    not_pair = set()     # frozenset({a,b}) — 같아 보였지만 실제로는 짝이 아니었음
    pending = None       # 방금 짝이라 믿고 눌러본 두 장 (다음 턴에 결과 확인)
    matched = set()
    t0 = time.time()
    _round_t0, _hurry_on = t0, True     # 이 시점부터 '서두름' 계산 시작
    clicks = bombs = wrong = 0
    stuck = 0

    def stats():
        return {"clicks": clicks, "bombs": bombs, "wrong": wrong,
                "secs": round(time.time() - t0, 1), "matched": len(matched)}

    while running and alive:
        if time.time() - t0 > ROUND_TIMEOUT:
            print(f"  [중단] 한 판이 {ROUND_TIMEOUT}초를 넘김")
            _hurry_on = False
            return False, stats()
        if not window_open(sct):
            if verbose:
                print(f"  창이 닫힘 → 한 판 완료 (클릭 {clicks}회, 폭탄 {bombs}회, "
                      f"{time.time()-t0:.0f}초)")
            _hurry_on = False
            return True, stats()

        # 카드를 고를 때는 상태(뒷면/열림)만 보면 되고, 상태 판정은 카드 테두리
        # 색으로 하므로 커서에 거의 영향받지 않음 → 여기선 커서를 안 치움
        states, _ = read_board(sct)

        # ---- 이번 턴에 처음 누를 카드 정하기 ----
        pair = find_known_pair(memory, not_pair)
        if pair:
            _, first, second = pair          # 확정 짝을 노림
        else:
            think_pause()          # 어디를 열어볼지 고민하는 흔적
            first, second = pick_unknown(states, memory), None
            if first is None:
                # 안 본 카드가 없음 = 기억이 낡았거나 폭탄만 남음.
                # 아무 뒷면 카드나 눌러서 상황을 진행시킴 (폭탄이면 판이 섞임)
                backs = [p for p, s in states.items() if s == "?"]
                if not backs:
                    time.sleep(0.3)
                    continue
                stuck += 1
                if stuck > 6:
                    memory.clear()
                    not_pair.clear()
                    stuck = 0
                first = random.choice(backs)

        # ---- 첫 클릭 ----
        click_card(card_center(*first))
        clicks += 1
        states, images = wait_flip(sct, first, "?")
        if states.get(first) != "X" and second is None:
            # 이 카드의 그림을 기억해야 하므로 커서를 치우고 깨끗하게 다시 읽음
            states, images = read_clean(sct)

        # 첫 클릭 직후에는 '맞춘 카드'만 열려있음 (틀린 두 장은 이 클릭에 닫힘)
        matched = {p for p, s in states.items() if s == "O" and p != first}
        memory = {p: m for p, m in memory.items() if p not in matched}

        # ---- 직전에 시도한 짝이 실제로 맞았는지 게임에게 확인 ----
        if pending:
            a, b, ia, ib = pending
            if a in matched and b in matched:
                if verbose:
                    print(f"  ✔ 짝 맞춤 ({a[0]+1},{a[1]+1}) + ({b[0]+1},{b[1]+1})")
            else:
                # 그림이 비슷해서 오판한 것 → 조합을 기억하고 카드는 기억에 되돌림
                not_pair.add(frozenset((a, b)))
                memory[a], memory[b] = ia, ib
                wrong += 1
                if verbose:
                    print(f"  ✗ ({a[0]+1},{a[1]+1}) + ({b[0]+1},{b[1]+1}) 는 짝이 아니었음"
                          f" → 이 조합은 다시 안 씀")
            pending = None

        if states.get(first) == "X":
            if verbose:
                print(f"  💣 폭탄 ({first[0]+1},{first[1]+1}) → 자리가 섞임, 기억 초기화")
            memory.clear()
            not_pair.clear()
            bombs += 1
            continue
        if first not in images:
            continue                         # 못 읽음 → 다음 바퀴에 다시
        img1 = images[first]
        memory[first] = img1
        stuck = 0

        # ---- 확정 짝을 노린 턴이면 두 번째 카드도 클릭 ----
        if second is not None:
            click_card(card_center(*second))
            clicks += 1
            wait_flip(sct, second, "?")
            # 시도한 두 장은 기억에서 빼둠 — 안 그러면 다음 턴에 또 같은 짝을
            # 고르고, 그 클릭 때문에 위 검증이 헛나감
            pending = (first, second, memory.pop(first, img1),
                       memory.pop(second, img1))
            continue

        # ---- 탐색 턴: 기억에 같은 그림이 있으면 바로 짝 시도 ----
        m = find_match(img1, memory, not_pair, first)
        if m:
            _, b = m
            click_card(card_center(*b))
            clicks += 1
            wait_flip(sct, b, "?")
            pending = (first, b, memory.pop(first, img1), memory.pop(b, img1))
            continue

        # ---- 모르는 카드를 한 장 더 열어봄 (정보 최대화) ----
        c2 = pick_unknown(states, memory, exclude={first})
        if c2 is None:
            continue
        click_card(card_center(*c2))
        clicks += 1
        states2, images2 = wait_flip(sct, c2, "?")
        if states2.get(c2) != "X":
            states2, images2 = read_clean(sct)     # 커서 치우고 깨끗하게
        if states2.get(c2) == "X":
            if verbose:
                print(f"  💣 폭탄 ({c2[0]+1},{c2[1]+1}) → 자리가 섞임, 기억 초기화")
            memory.clear()
            not_pair.clear()
            bombs += 1
            continue
        if c2 not in images2:
            continue
        memory[c2] = images2[c2]
        if diff(img1, images2[c2]) <= SAME_DIFF and frozenset((first, c2)) not in not_pair:
            pending = (first, c2, memory.pop(first, img1),
                       memory.pop(c2, images2[c2]))   # 탐색하다 우연히 짝을 뽑음
            if verbose:
                print(f"  · 탐색 중 같은 그림 발견 ({first[0]+1},{first[1]+1})"
                      f" + ({c2[0]+1},{c2[1]+1})")

    _hurry_on = False
    return False, stats()


# ==================== 재료 넣기 (auto_cook.py 와 같은 방식) ====================

def load_templates():
    """items 폴더의 png를 {재료이름: [이미지,...]} 로 불러옴."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items")
    templates = {}
    if not os.path.isdir(folder):
        return templates
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".png") or fn.startswith("cell_"):
            continue
        stem = os.path.splitext(fn)[0]
        base = re.sub(r"[_\-]?\d+$", "", stem) or stem
        img = np.array(Image.open(os.path.join(folder, fn)).convert("RGB"), dtype=int)
        templates.setdefault(base, []).append(img[:CELL_SIZE, :CELL_SIZE])
    return templates


def match_region(region, tpl):
    """region 안에서 tpl 을 밀어가며 가장 잘 맞는 위치의 차이값을 반환."""
    tb = tpl[TOP_CUT:CELL_SIZE, :CELL_SIZE]
    tb_fg = tb.sum(axis=2) > 90
    hh, ww = tb.shape[:2]
    n = 2 * ALIGN + 1
    sub = region[TOP_CUT:TOP_CUT + n + hh - 1, :n + ww - 1]
    windows = np.lib.stride_tricks.sliding_window_view(sub, (hh, ww, 3))[:, :, 0]
    win_fg = windows.sum(axis=-1) > 90
    fg = tb_fg[None, None] | win_fg
    fg_count = fg.sum(axis=(-2, -1))
    diff_sum = np.where(fg, np.abs(windows - tb).sum(axis=-1), 0).sum(axis=(-2, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = diff_sum / (fg_count * 3)
    valid = fg_count >= 20
    if not valid.any():
        return 1e9
    return float(np.where(valid, d, np.inf).min())


def scan_inventory(sct, templates):
    """인벤토리 전체를 스캔. {재료이름: [칸 중심좌표,...]} 와 최소차이값 반환."""
    park_mouse()
    found = {}
    min_diffs = {name: 1e9 for name in templates}
    size = CELL_SIZE + 2 * ALIGN
    for r in range(ROWS):
        for c in range(COLS):
            nx = int(round(CELL1_CENTER[0] + c * PITCH_X))
            ny = int(round(CELL1_CENTER[1] + r * PITCH_Y))
            region = grab(sct, nx, ny, size // 2)[:size, :size]
            center = region[ALIGN + TOP_CUT:ALIGN + CELL_SIZE, ALIGN:ALIGN + CELL_SIZE]
            if int((center.sum(axis=2) > 90).sum()) < MIN_ITEM_PX:
                continue
            best_name, best_diff = None, 1e9
            for name, tpls in templates.items():
                for tpl in tpls:
                    d = match_region(region, tpl)
                    if d < min_diffs[name]:
                        min_diffs[name] = d
                    if d < best_diff:
                        best_name, best_diff = name, d
            if best_name is not None and best_diff <= threshold_for(best_name):
                found.setdefault(best_name, []).append((nx, ny))
    return found, min_diffs


def cell_still_has(sct, templates, name, pos):
    """넣기 직전 검증 — 그 칸이 '진짜로' 그 재료인지 확인.

    기준 이하이기만 하면 통과시키면 안 됨: 재료끼리 조금 닮으면 다른 재료도
    기준 안에 들어와서 엉뚱한 게 들어감. 그래서 스캔과 똑같이 '모든 재료 중
    이게 가장 잘 맞는지'까지 확인함.
    """
    size = CELL_SIZE + 2 * ALIGN
    region = grab(sct, int(round(pos[0])), int(round(pos[1])), size // 2)[:size, :size]
    center = region[ALIGN + TOP_CUT:ALIGN + CELL_SIZE, ALIGN:ALIGN + CELL_SIZE]
    if int((center.sum(axis=2) > 90).sum()) < MIN_ITEM_PX:
        return False
    best_name, best_diff = None, 1e9
    for other, tpls in templates.items():
        for tpl in tpls:
            d = match_region(region, tpl)
            if d < best_diff:
                best_name, best_diff = other, d
    if best_name != name:
        print(f"       (칸 확인: '{name}' 인 줄 알았는데 '{best_name}' 가 더 잘 맞음) → 안 씀")
        return False
    return best_diff <= threshold_for(name)


def slot_px(sct, i):
    """슬롯 '중앙'의 밝은 픽셀 수 (전체를 보면 배경이 섞여 오판함)."""
    cx = int(SLOT1_CENTER[0] + i * SLOT_PITCH_X)
    cy = int(SLOT1_CENTER[1])
    img = grab(sct, cx, cy, SLOT_CHECK // 2)
    return int((img.sum(axis=2) > 90).sum())


def slot_filled(sct, i):
    return slot_px(sct, i) >= MIN_SLOT_PX


def filled_slots(sct, n):
    return [i for i in range(n) if slot_filled(sct, i)]


def fill_slots(sct, templates):
    """레시피대로 재료를 우클릭으로 넣음. 성공하면 True."""
    global _scan_cache, _rounds_since_scan
    if not RECIPE:
        print("  (RECIPE 가 비어 있음 → 재료 넣기 건너뜀)")
        return True

    plan = [name for name, cnt in RECIPE for _ in range(cnt)]
    if len(plan) > NUM_SLOTS:
        print(f"[중단] 레시피 재료 수({len(plan)})가 슬롯({NUM_SLOTS}칸)보다 많음")
        return False

    if _scan_cache is not None and _rounds_since_scan < SCAN_EVERY:
        found = _scan_cache
        print(f"인벤토리 스캔 생략 — 지난 결과 재사용 ({_rounds_since_scan+1}/{SCAN_EVERY}판째)")
        min_diffs = {}
    else:
        found, min_diffs = scan_inventory(sct, templates)
        _scan_cache, _rounds_since_scan = found, 0
        print("인벤토리 인식:", {k: len(v) for k, v in found.items()})

    need = {}
    for name, cnt in RECIPE:
        need[name] = need.get(name, 0) + cnt

    # 우클릭은 같은 칸을 여러 번 눌러서 여러 개를 넣을 수 있음(한 칸에 최대 20개까지
    # 쌓임). 그래서 '칸 수 >= 필요 개수'를 요구하면 안 되고, 재료가 한 칸이라도
    # 인식되면 일단 진행함. 실제로 모자라면 아래 넣기 단계에서 잡힘.
    missing = [n for n in need if not found.get(n)]
    if missing and _rounds_since_scan > 0:
        print("  재사용한 결과에 재료가 안 보임 → 즉시 다시 스캔")
        found, min_diffs = scan_inventory(sct, templates)
        _scan_cache, _rounds_since_scan = found, 0
        missing = [n for n in need if not found.get(n)]
    if missing:
        for n in missing:
            print(f"[중단] 재료 '{n}' 을 인벤토리에서 못 찾음"
                  + (f" · 가장 비슷한 칸 차이 {min_diffs.get(n,0):.1f}"
                     f" (인식 기준 {threshold_for(n)} 이하)" if min_diffs else ""))
        _scan_cache = None
        return False

    target = len(plan)
    px = [slot_px(sct, i) for i in range(target)]
    filled = sum(1 for v in px if v >= MIN_SLOT_PX)
    if filled:
        print(f"  [주의] 넣기 전인데 슬롯 {filled}칸이 '이미 참'으로 읽힘 — 밝은픽셀 {px}")

    used = {}
    for name in plan:
        if filled >= target:
            break
        placed = False
        while running and alive and not placed:
            idx = used.get(name, 0)
            if idx >= len(found.get(name, [])):
                break
            src = found[name][idx]
            if not cell_still_has(sct, templates, name, src):
                used[name] = idx + 1
                continue
            print(f"  '{name}' 우클릭으로 넣기 ({filled+1}/{target})")
            right_click_item(src)
            now = len(filled_slots(sct, target))
            if now > filled:
                filled = now
                placed = True        # 성공한 칸은 그대로 둠 (여러 개 쌓여 있으면 계속 씀)
            else:
                print(f"    [재시도] 안 들어감 → '{name}' 의 다른 칸에서")
                used[name] = idx + 1
        if not placed:
            print(f"[중단] '{name}' 를 더 넣지 못함 ({filled}/{target} 채움)"
                  f" — 재료가 실제로 부족하거나 넣기가 계속 실패함")
            _scan_cache = None
            return False

    empty = [i + 1 for i in range(target) if not slot_filled(sct, i)]
    if empty:
        print(f"[중단] 시작 직전 확인 — 슬롯 {empty} 이 비어 있음")
        _scan_cache = None
        return False
    print(f"  재료 {target}개 전부 들어간 것 확인")
    _rounds_since_scan += 1
    return True


# ==================== 창 열기 / 한 판 진행 ====================

def open_furniture_window(sct):
    """직업 → 직업활동 순서로 눌러 가구만들기 창을 엶."""
    if window_open(sct):
        return True
    print("가구만들기 창이 안 보임 → 다시 열기")
    direct_click(JOB_BTN, "직업")
    time.sleep(random.uniform(0.7, 1.1))
    direct_click(JOB_ACT_BTN, "직업활동")
    for _ in range(20):
        time.sleep(0.25)
        if window_open(sct):
            print("  가구만들기 창 열림 확인")
            return True
    print("  [실패] 가구만들기 창이 안 열림")
    return False


def press_start(sct):
    """시작 버튼을 누르고, 카드판이 실제로 시작됐는지 확인."""
    human_click(START_BTN)
    print("  시작 버튼 클릭!")
    t0 = time.time()
    while time.time() - t0 < 6:
        time.sleep(0.25)
        if not window_open(sct):
            return False
        states, _ = read_board(sct)
        if sum(1 for s in states.values() if s in ("?", "O", "X")) >= 20:
            return True
    return False


def run_one_round(sct, templates):
    global _rounds_done
    if not open_furniture_window(sct):
        return False
    if not fill_slots(sct, templates):
        return False
    if not press_start(sct):
        print("  [중단] 시작 후 카드판이 안 보임")
        return False
    ok, stats = play_board(sct)
    if not ok:
        return False
    print(f"  (클릭 {stats['clicks']}회 · 폭탄 {stats['bombs']}회 · {stats['secs']}초)")
    _rounds_done += 1
    print(f"★ 한 판 완료! (누적 {_rounds_done}판)")
    time.sleep(random.uniform(1.0, 2.0))
    return True


# ==================== 메인 ====================

def toggle():
    global running, _scan_cache
    _scan_cache = None
    running = not running
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨")


def quit_all():
    global alive, running
    running = False
    alive = False
    print("\n종료합니다...")


def worker():
    global running, alive
    try:
        templates = load_templates()
        recipe_names = {n for n, _ in RECIPE}
        templates = {k: v for k, v in templates.items() if k in recipe_names}
        if RECIPE:
            if not templates:
                print("[주의] items 폴더에 RECIPE 재료 아이콘이 없음 "
                      "— capture_items.py 로 먼저 등록하세요")
            else:
                print("등록된 재료:", ", ".join(templates))
                missing = recipe_names - templates.keys()
                if missing:
                    print(f"[주의] 아이콘이 없는 재료: {', '.join(missing)}")
        else:
            print("RECIPE 가 비어 있음 → 재료 넣기 없이 시작 버튼만 누름")

        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.15)
                    continue
                ok = run_one_round(sct, templates)
                if not ok:
                    if not (running and alive):
                        continue
                    print(f"[오류] 한 판 실패 — {AUTO_RESTART_SEC}초 뒤 자동 재시작 "
                          f"(즉시 재개 F8, 종료 F9)")
                    t0 = time.time()
                    while running and alive and time.time() - t0 < AUTO_RESTART_SEC:
                        time.sleep(0.2)
                    continue
                if not LOOP:
                    running = False
                    print("정지 (LOOP=False). 다시 하려면 F8.")
    except pyautogui.FailSafeException:
        print("\n[비상정지] 마우스가 화면 구석으로 갔습니다. 완전히 종료합니다.")
        alive = False
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        alive = False


def main():
    print("=" * 52)
    print(" 가구만들기 그림맞추기 풀 자동 봇")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 52)
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
