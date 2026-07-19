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
import re
import time
import random
import threading
import urllib.parse
import urllib.request

import mss
import numpy as np
import pyautogui
import keyboard
from PIL import Image

# ===================== 온도계 / 버튼 (이 컴퓨터 좌표 고정) =====================
GAUGE_LEFT   = 1046
GAUGE_TOP    = 132
GAUGE_WIDTH  = 20
GAUGE_HEIGHT = 85

PLUS_BTN  = (1179, 284)
MINUS_BTN = (1257, 284)
BTN_JITTER = 9
START_BTN = (1152, 388)

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
LOOKAHEAD    = 1.2      # 속도로 이 초만큼 앞을 예측 (크게=더 일찍 뗌, 작게=늦게 뗌) — 오버슈트 줄이려 1.0→1.2
CTRL_DEADBAND = 0.04    # 위치가 목표 중심에서 이 안이면 적정으로 보고 안 누름
HOLD_MIN     = 0.2      # 한 번 누르면 최소 이만큼은 꾹 (짧은 뽀짝 누름 방지) — 오버슈트 커서 0.3→0.2
HOLD_MAX     = 6.5      # 한 번에 최대 이만큼까지만 꾹 (안전용 상한 — 게임 업데이트로 초반에
                        # +를 6초 정도 길게 눌러야 해서 6.5로 널널하게. 어차피 예측이
                        # 중심에 닿으면 알아서 미리 떼므로 필요한 만큼만 꾹 누르게 됨)
HOLD_GAP     = (0.25, 0.5)   # 뗀 뒤 기다리는 시간(초) — 길면 그 사이 관성으로 넘쳐서 0.6~1.1→0.25~0.5로 줄임
REPRESS_SEC  = 2.4      # 같은 방향을 다시 누르기까지 최소 간격 — 짧게 여러 번 누르는 대신
                        # 한 번 길게 누르고 오래 기다리는 쪽으로 1.6→2.4
STALL_V      = 0.04     # 이 속도(/초)보다 느리면 '멈춘 것'으로 봄
VEL_WINDOW   = 0.22     # 속도를 이 초 구간의 위치 변화로 계산 (노이즈 완화)
SAMPLE_DT  = 0.03
DONE_NONE_SEC = 1.2     # 창이 닫힌 채 수은이 이만큼 안 보이면 요리 끝으로 판단
MIN_ROUND_SEC = 6.0     # 시작 후 이 시간 전엔 '요리 끝'으로 판단 안 함 (오검출 방지)
NO_MERCURY_SEC = 15     # 시작 클릭 후 이 시간 동안 수은이 한 번도 안 보이면
                        # 시작 자체가 실패한 것(슬롯 비었음 등)으로 보고 일찍 접음

# (구 방식 파라미터 — 지금은 안 씀, 참고용)
MOMENTUM_UP   = 0.06
MOMENTUM_DOWN = 0.03
DEADBAND   = 0.03

# ===================== 인벤토리 / 슬롯 (이 컴퓨터 좌표 고정) =====================
CELL1_CENTER = (772, 65)   # 인벤토리 첫 칸(왼쪽 위) 중심 좌표
PITCH_X = 42.2          # 옆 칸까지 가로 간격
PITCH_Y = 41.5          # 아래 칸까지 세로 간격
COLS = 6
ROWS = 5
CELL_SIZE = 32          # capture_items.py와 같은 값
SEARCH_MARGIN = 4       # 계산된 칸 위치가 어긋나도 실제 아이콘 중심을 스스로 찾는 여유 범위
                        # (칸 간격 41px보다 너무 넓으면 옆 칸까지 침범해서 오작동하니 좁게)

SLOT1_CENTER = (1083, 86)  # 요리창 재료 슬롯 1번(맨 왼쪽 검은 칸) 중심
SLOT_PITCH_X = 51       # 슬롯 간 가로 간격
NUM_SLOTS = 5           # 지금 열려있는 슬롯 수 (5개 열리면 5로)

# ===================== 레시피 =====================
# (재료이름, 넣을 개수) — 이름은 items 폴더의 파일명과 똑같이.
# 개수만큼 드래그함 (슬롯 1번부터 차례로). 합계는 슬롯 수(5) 이하로.
RECIPE = [
    ("버섯", 1),
    ("쌀", 1),
    ("최상급향신료", 3),
]

LOOP = True             # True면 재료가 떨어질 때까지 자동 반복 (False면 한 판만)
SCAN_EVERY = 5          # 인벤토리 스캔 주기(판) — 재료 양이 많아 칸 배치가 자주 안 바뀌므로
                        # 5판에 1번만 스캔하고 나머지는 지난 결과를 재사용.
                        # 오류가 나거나 재료가 모자라 보이면 즉시 다시 스캔함.

# ----- 요리창 다시 열기 (LOOP용) -----
# 요리가 끝나면 음식만들기 창이 닫히므로, 반복하려면 다시 여는 클릭이 필요.
# JOB_BTN     = 화면 아래 메뉴의 "직업" 아이콘 중심 좌표.
#               직업 창이 요리 중에도 계속 열려있다면 None으로 (클릭 생략).
# JOB_ACT_BTN = 직업 창의 "직업활동" 버튼 중심 좌표.
JOB_BTN     = (437, 698)     # 아래 메뉴바의 "직업" 아이콘
JOB_ACT_BTN = (685, 246)     # 직업 창의 "직업활동" 버튼
GAUGE_BG_RGB = (40, 88, 47)   # 음식만들기 창의 온도계 주변 진초록 (열림 확인용)
REOPEN_WAIT = 8         # 창 열림 최대 대기(초)
MATCH_THRESHOLD = 50    # 기본 인식 기준 (차이값) — 실사용 결과 50이 잘 맞음. 오인식하면 낮추기
# 재료별로 다른 기준이 필요하면 여기에 추가 (예: {"버섯": 45})
MATCH_THRESHOLDS = {}


def threshold_for(name):
    return MATCH_THRESHOLDS.get(name, MATCH_THRESHOLD)
TOP_CUT = 13            # 칸 위쪽 수량 숫자 영역을 가림 (이 픽셀만큼 위 무시)
SHIFT = 2               # (구) 좌표 미세 어긋남 보정 — 지금은 ALIGN이 대체
ALIGN = 7               # 아이콘을 상하좌우 ±이 픽셀까지 밀어보며 가장 잘맞는 위치를 찾음
                        # (밝은픽셀 평균 방식이 숫자배지에 끌려 불안정하던 문제 해결. 창이 조금 밀려도 흡수)
MIN_ITEM_PX = 40        # 칸 중앙에 밝은 픽셀이 이보다 적으면 빈 칸으로 봄
MIN_SLOT_PX = 40        # 요리창 슬롯 안 밝은 픽셀이 이보다 적으면 '빈 슬롯'으로 봄 (드래그 검증용)
COOK_TIMEOUT = 90       # 요리 1판 최대 대기(초)

# ----- 오류 자가복구 / 자동 재시작 -----
# 오류가 나면 먼저 스스로 점검(좌표 재보정 → 요리창 다시 열기 → 가방 열기 →
# 인벤토리 재스캔)하고 곧바로 재시도함. 연속으로 MAX_FIX_TRIES번 실패하면
# 그때는 RETRY_SEC 뒤에 자동으로 F8을 누른 것처럼 다시 시작함.
# RETRY_SEC=None이면 자동 재시작 안 함. 사용자가 직접 F8로 끈 경우엔 둘 다 안 함.
RETRY_SEC = 60
MAX_FIX_TRIES = 3

# ----- 가방(아이템 창) 자동 열기 -----
# 재료 넣기 전에 가방(아이템) 창이 안 보이면 자동으로 한 번 열어봄.
# 열 방법을 하나는 설정해야 함: 단축키가 있으면 BAG_KEY, 없으면 BAG_BTN(아이콘 좌표).
BAG_KEY = None            # 가방 여는 키보드 단축키 (예: "b"). 없으면 None
BAG_BTN = None            # 아래 메뉴바의 가방(아이템) 아이콘 중심 좌표 — measure.py로 측정 (예: (390, 698))
BAG_WAIT = 6              # 가방 창 열림 최대 대기(초)

# ----- 텔레그램 알림 -----
# 오류나 재료 부족으로 멈추면 텔레그램으로 알려줌. 설정 방법:
#  1) 텔레그램 앱에서 @BotFather 검색 → /newbot → 이름 정하면 토큰을 줌
#  2) 방금 만든 봇과의 대화방에서 아무 메시지나 하나 보내기
#  3) 브라우저에서 https://api.telegram.org/bot<토큰>/getUpdates 를 열면
#     "chat":{"id":123456789,... 에 보이는 숫자가 chat_id
# 두 값을 다 채우면 알림이 켜짐. 비워두면 알림 없이 기존처럼 동작.
TELEGRAM_TOKEN   = ""    # ← 다운로드 후 각 컴퓨터에서 봇 토큰을 여기 붙여넣기
TELEGRAM_CHAT_ID = ""    # ← chat_id도 여기에 (저장소가 공개라서 깃허브엔 안 올림)
NOTIFY_NAME      = "규남노트북"   # 알림 앞에 붙는 이름 — 컴퓨터마다 다르게 (예: "정희노트북")
NOTIFY_COOLDOWN  = 600    # 같은 내용의 알림을 다시 보내기까지 최소 간격(초) — 도배 방지
REPORT_EVERY_MIN = 30     # 이 간격(분)마다 누적 완료 판수를 현황 보고로 보냄. 0이면 끔
SEND_SCREENSHOT  = True   # 현황보고/오류 알림에 화면 스크린샷을 같이 보낼지
SHOT_MAX_W       = 1920   # 스크린샷 가로 최대 폭(px) — 넘으면 축소해서 전송(용량/속도)

# (컴퓨터별 프로필/자동 추적 기능은 제거함 — 위 좌표를 이 컴퓨터에 고정으로 사용.
#  게임 창을 옮기지 말고 그대로 둘 것. 다른 컴퓨터에서 쓰려면 위 좌표들을
#  그 컴퓨터에서 measure.py로 다시 재서 직접 바꿔주면 됨.)

# ===================== 창 자동 추적 (꺼짐 — 아래 WINDOW_FOLLOW=False) =====================
# 각 UI가 어느 게임 창 소속인지 알고, 실행 중 그 창의 현재 위치를 찾아
# "기준 위치에서 움직인 만큼" 좌표를 자동 보정함. → 창 옮겨도 재측정 불필요.
# (창 크기는 그대로 두어야 함. 크기를 바꾸면 재측정 필요)
WINDOW_FOLLOW = False   # 창 추적 끔 — 프로필/기본값의 고정좌표만 사용. 창을 옮기면 안 됨
# 좌표를 측정했던 당시의 각 창 왼쪽위(left, top) — pygetwindow로 확인한 값
REF_COOK = (3088, 0)    # "음식만들기" 창
REF_ITEM = (2815, 0)    # "아이템" 창
REF_JOB  = (2557, 0)    # "직업" 창
# JOB_BTN(아래 메뉴바 직업 아이콘)은 메인 게임창 소속이라 추적 안 함 — 메인창 옮기면 재측정
# ==============================================================================

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

running = False
alive = True
retry_at = None          # 오류로 멈춘 뒤 자동 재시작할 시각 (None이면 예약 없음)
_fail_streak = 0         # 연속 실패 횟수 — 한 판 성공하면 0으로 리셋
_scan_cache = None       # 마지막 인벤토리 스캔 결과 {이름: [좌표,...]}
_rounds_since_scan = 0   # 마지막 스캔 이후 재료를 넣은 판 수
_fail_detail = ""        # 마지막 실패의 상세 내용 (알림 메시지에 덧붙임)
_last_notify = {}        # 알림 종류별 마지막 전송 시각 (같은 내용 도배 방지)
_rounds_done = 0         # 프로그램 시작 후 완료한 판 수 (누적)
_session_t0 = time.time()        # 프로그램 시작 시각
_last_report = time.time()       # 마지막 현황 보고 시각
_rounds_at_report = 0            # 마지막 보고 시점의 누적 판수 (최근 증가분 계산용)

# 측정된 원본 좌표 보관 (창 이동 보정의 기준값). recalibrate가 여기에 delta를 더함.
_BASE_COORD = {
    "GAUGE_LEFT": GAUGE_LEFT, "GAUGE_TOP": GAUGE_TOP,
    "PLUS_BTN": PLUS_BTN, "MINUS_BTN": MINUS_BTN, "START_BTN": START_BTN,
    "SLOT1_CENTER": SLOT1_CENTER, "CELL1_CENTER": CELL1_CENTER,
    "JOB_ACT_BTN": JOB_ACT_BTN,
}

try:
    import pygetwindow as _gw
except Exception:
    _gw = None
    WINDOW_FOLLOW = False


def _win_origin(title, ref=None):
    """제목이 정확히 title인 창의 (left, top). 못 찾으면 None.

    같은 제목의 창이 여러 개 잡히면(이전 세션의 유령 창 등) ref(기준 위치)에
    제일 가까운 걸 골라서, 엉뚱한 창을 잡아 좌표가 크게 튀는 걸 방지함.
    """
    if not (WINDOW_FOLLOW and _gw):
        return None
    try:
        cands = [(w.left, w.top) for w in _gw.getAllWindows()
                 if w.title == title and w.width > 0]
    except Exception:
        return None
    if not cands:
        return None
    if len(cands) > 1 and ref is not None:
        cands.sort(key=lambda p: (p[0] - ref[0]) ** 2 + (p[1] - ref[1]) ** 2)
    return cands[0]


def _win_origin_stable(title, ref=None, tries=8, gap=0.12):
    """창이 막 열리는 중이면 슬라이드/애니메이션으로 위치가 흔들릴 수 있어서,
    연속으로 같은 값이 두 번 나올 때까지 기다렸다가 반환 (최대 tries번)."""
    last = None
    for _ in range(tries):
        o = _win_origin(title, ref=ref)
        if o is not None and o == last:
            return o
        last = o
        time.sleep(gap)
    return last


def recalibrate(which="all"):
    """열려있는 창의 현재 위치를 찾아, 소속 좌표들을 기준+이동량으로 갱신.

    JOB_ACT_BTN(직업활동 버튼)은 창 위치 추적에서 제외함 — '직업' 창 감지가
    엉뚱한 값을 반환하는 문제가 있어, 고정 좌표를 그대로 씀(직업 버튼 누르고
    바로 그 고정 좌표로 이동해 클릭).
    """
    global GAUGE_LEFT, GAUGE_TOP, PLUS_BTN, MINUS_BTN, START_BTN
    global SLOT1_CENTER, CELL1_CENTER
    if not WINDOW_FOLLOW:
        return
    B = _BASE_COORD
    if which in ("all", "cook"):
        o = _win_origin_stable("음식만들기", ref=REF_COOK)
        if o:
            dx, dy = o[0] - REF_COOK[0], o[1] - REF_COOK[1]
            GAUGE_LEFT = B["GAUGE_LEFT"] + dx
            GAUGE_TOP = B["GAUGE_TOP"] + dy
            PLUS_BTN = (B["PLUS_BTN"][0] + dx, B["PLUS_BTN"][1] + dy)
            MINUS_BTN = (B["MINUS_BTN"][0] + dx, B["MINUS_BTN"][1] + dy)
            START_BTN = (B["START_BTN"][0] + dx, B["START_BTN"][1] + dy)
            SLOT1_CENTER = (B["SLOT1_CENTER"][0] + dx, B["SLOT1_CENTER"][1] + dy)
    if which in ("all", "item"):
        o = _win_origin_stable("아이템", ref=REF_ITEM)
        if o:
            dx, dy = o[0] - REF_ITEM[0], o[1] - REF_ITEM[1]
            CELL1_CENTER = (B["CELL1_CENTER"][0] + dx, B["CELL1_CENTER"][1] + dy)

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
    # 뗀 직후 반대 버튼 위로 미리 이동해 대기 (사람처럼) → 넘치는 순간 이동 없이 바로 누름
    opposite = MINUS_BTN if sign > 0 else PLUS_BTN
    ox, oy = jittered(opposite)
    smooth_move_to(ox, oy, random.uniform(0.12, 0.22), bow=5)
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


def direct_click(point, label, jx=4, jy=4):
    """곡선(bow) 없이 직선으로 곧장 이동해서 확실하게 클릭. 좌표를 로그로 출력함.

    직업/직업활동처럼 위치가 확실한 작은 버튼은 화려한 곡선 이동이 오히려
    "누르는지 안 누르는지 애매하게" 보이게 만들어서, 이 버튼들엔 이걸 씀.
    """
    x = point[0] + random.randint(-jx, jx)
    y = point[1] + random.randint(-jy, jy)
    print(f"  {label} 클릭 → ({x}, {y})")
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.35))
    time.sleep(random.uniform(0.12, 0.2))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.1, 0.18))
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
    """items 폴더의 png를 불러옴. {재료이름: [이미지, 이미지, ...]} 형태로 반환.

    같은 재료를 수량별로 다르게 생긴 여러 장 등록할 수 있도록, 파일명 끝의
    숫자는 무시하고 묶음. 예: 버섯1.png, 버섯2.png, 버섯20.png → 전부 "버섯".
    """
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items")
    templates = {}
    if not os.path.isdir(folder):
        return templates
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".png") or fn.startswith("cell_"):
            continue
        stem = os.path.splitext(fn)[0]
        base = re.sub(r"[_\-]?\d+$", "", stem) or stem   # 끝 숫자 제거해 그룹화
        img = np.array(Image.open(os.path.join(folder, fn)).convert("RGB"), dtype=int)
        templates.setdefault(base, []).append(img[:CELL_SIZE, :CELL_SIZE])
    return templates


def match_region(region, tpl):
    """region(=CELL_SIZE+2*ALIGN 정사각형) 안에서 tpl(32x32)을 상하좌우로 밀어가며
    가장 잘 맞는(차이 최소) 위치를 찾아 그 차이값을 반환.

    - 위쪽 TOP_CUT 만큼은 수량 숫자라 비교에서 제외
    - 검은 배경이 아닌 부분(그림 있는 부분)만 비교 (배경끼리 항상 맞아 희석되는 것 방지)
    - 밝은픽셀 평균으로 중심 잡던 예전 방식은 어두운 버섯이 옆 숫자배지에 끌려
      크롭이 흔들렸음 → 아예 여러 위치를 직접 대보고 최적을 고름
    """
    # 225번(15x15) 오프셋을 파이썬 for문으로 하나씩 슬라이싱/비교하면 느린 CPU에서
    # 함수 호출 오버헤드가 누적돼 눈에 띄게 느려짐 → sliding_window_view로 한 번에
    # 벡터 연산 (결과는 기존 for문과 수학적으로 동일, 훨씬 빠름)
    tb = tpl[TOP_CUT:CELL_SIZE, :CELL_SIZE]        # 숫자영역 제외한 템플릿
    tb_fg = tb.sum(axis=2) > 90
    hh, ww = tb.shape[:2]
    n = 2 * ALIGN + 1
    sub = region[TOP_CUT:TOP_CUT + n + hh - 1, :n + ww - 1]
    windows = np.lib.stride_tricks.sliding_window_view(sub, (hh, ww, 3))[:, :, 0]
    win_fg = windows.sum(axis=-1) > 90
    fg = tb_fg[None, None] | win_fg                # (n, n, hh, ww)
    fg_count = fg.sum(axis=(-2, -1))                # (n, n)
    diff_sum = np.where(fg, np.abs(windows - tb).sum(axis=-1), 0).sum(axis=(-2, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = diff_sum / (fg_count * 3)
    valid = fg_count >= 20
    if not valid.any():
        return 1e9
    return float(np.where(valid, d, np.inf).min())


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


def park_mouse():
    """스캔 전에 마우스를 인벤토리 밖 빈 곳으로 치워둠 (커서가 아이콘 덮는 것 방지)."""
    px = int(CELL1_CENTER[0])
    py = int(CELL1_CENTER[1] + ROWS * PITCH_Y + 55)   # 마지막 줄 아래 = 아이템 정보 패널(빈 곳)
    smooth_move_to(px, py, random.uniform(0.15, 0.3), bow=8)
    time.sleep(random.uniform(0.1, 0.2))


def save_debug_scan(sct, tag="debug_scan"):
    """인벤토리 영역 전체를 캡처해 파일로 저장 (인식 실패 원인 눈으로 확인용)."""
    from PIL import Image as _Image
    left = int(CELL1_CENTER[0] - PITCH_X)
    top = int(CELL1_CENTER[1] - PITCH_Y)
    width = int((COLS + 1) * PITCH_X)
    height = int((ROWS + 1) * PITCH_Y)
    shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    img = np.asarray(shot, dtype="uint8")[:, :, :3][:, :, ::-1]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{tag}.png")
    _Image.fromarray(img).save(path)
    print(f"       [진단] 인벤토리 캡처를 저장함: {path}")
    return path


def scan_inventory(sct, templates):
    """인벤토리 전체를 스캔.

    반환: (found, min_diffs)
      found     = {재료이름: [칸 중심좌표, ...]}
      min_diffs = {재료이름: 전체 칸 중 가장 비슷했던 차이값}  ← 인식 실패 진단용
    """
    park_mouse()
    found = {}
    min_diffs = {name: 1e9 for name in templates}
    size = CELL_SIZE + 2 * ALIGN
    for r in range(ROWS):
        for c in range(COLS):
            nx = int(round(CELL1_CENTER[0] + c * PITCH_X))
            ny = int(round(CELL1_CENTER[1] + r * PITCH_Y))
            shot = sct.grab({"left": nx - size // 2, "top": ny - size // 2,
                             "width": size, "height": size})
            region = np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]
            # 빈 칸 판정: 중앙(칸 크기) 안에 밝은 픽셀이 거의 없으면 건너뜀
            center = region[ALIGN + TOP_CUT:ALIGN + CELL_SIZE, ALIGN:ALIGN + CELL_SIZE]
            if int((center.sum(axis=2) > 90).sum()) < MIN_ITEM_PX:
                continue
            best_name, best_diff = None, 1e9
            for name, tpl_list in templates.items():
                name_best = 1e9
                for tpl in tpl_list:
                    diff = match_region(region, tpl)
                    if diff < min_diffs[name]:
                        min_diffs[name] = diff
                    if diff < best_diff:
                        best_name, best_diff = name, diff
                    if diff < name_best:
                        name_best = diff
                    if name_best < 10:   # 이 재료의 다른 수량변형들도 이미 확실히 맞음 → 생략(속도)
                        break
                if best_diff < 15:      # 확실히 맞는 재료 찾음 → 나머지 템플릿 스킵 (속도)
                    break
            if best_name is not None and best_diff <= threshold_for(best_name):
                found.setdefault(best_name, []).append((nx, ny))
    return found, min_diffs


# ---------------------------------------------------------------- 단계별 동작

_bg = np.array(GAUGE_BG_RGB, dtype=int)


def window_open(sct):
    """음식만들기 창이 열려있는지 — 온도계 관 '바로 위'의 배경이 보이는지로 판단.

    관 자체(GAUGE_TOP~+HEIGHT)를 보면 요리 중엔 수은(빨강/노랑)이 채우고 있어서
    배경이 안 보이는 게 정상이라, 요리 중인데 "닫혔다"고 오판하게 됨.
    그래서 수은이 절대 닿지 않는, 관 바로 위쪽 얇은 띠만 확인함 — 여긴 창이
    열려있는 한 항상 배경색이어야 하고, 창이 실제로 닫힐 때만 사라짐.
    """
    region = {"top": max(GAUGE_TOP - 22, 0), "left": GAUGE_LEFT,
              "width": GAUGE_WIDTH, "height": 14}
    img = np.asarray(sct.grab(region), dtype=int)[:, :, :3][:, :, ::-1]
    near_bg = np.all(np.abs(img - _bg) <= 30, axis=-1)
    return near_bg.mean() > 0.5


def open_job_window():
    """직업 창이 '확실히' 열릴 때까지 처리. 열렸으면 True.

    직업 창이 안 열린 채 직업활동 좌표를 눌러봤자 허공 클릭이라,
    클릭 → 창 제목("직업")으로 열림 확인 → 안 열렸으면 다시 클릭 (최대 3번).
    이미 열려있으면 다시 안 누름 (토글로 닫혀버리는 것 방지).
    """
    if win_visible("직업") is True:
        print("직업 창 이미 열려있음")
        return True
    if JOB_BTN is None:
        print("[설정 필요] JOB_BTN(직업 아이콘 좌표)이 없고 직업 창도 안 보임")
        return False
    if win_visible("직업") is None:
        # pygetwindow로 확인 불가 → 예전 방식대로 클릭하고 시간만 기다림
        direct_click(JOB_BTN, "직업")
        time.sleep(random.uniform(1.2, 2.0))
        return True
    for attempt in range(3):
        direct_click(JOB_BTN, "직업")
        t0 = time.time()
        while running and alive and time.time() - t0 < 4:
            if win_visible("직업") is True:
                print("직업 창 열림 확인")
                time.sleep(random.uniform(0.6, 1.0))
                return True
            time.sleep(0.2)
        if not (running and alive):
            return False
        print(f"  직업 창이 안 열림 → 다시 클릭 ({attempt + 2}번째 시도)")
    print("[실패] 직업 창이 안 열림 — JOB_BTN 좌표 확인")
    return False


def reopen_window(sct):
    """직업 → 직업활동 클릭으로 음식만들기 창을 다시 염. 성공하면 True.

    게임 구조: 직업 창을 연 뒤 '직업활동'을 누르면 음식만들기 창이 생기고
    직업 창은 사라짐. 그래서 순서마다 실제로 됐는지 확인하고 안 됐으면 재시도:
      1) 직업 창이 열린 것을 확인 (open_job_window)
      2) 직업활동 클릭 → 음식만들기 창이 뜨는지 확인, 안 뜨면 다시 클릭 (최대 3번)
    """
    if JOB_ACT_BTN is None:
        print("[설정 필요] JOB_ACT_BTN(직업활동 버튼 좌표)이 없어서 반복 불가")
        return False
    if not open_job_window():
        return False
    for attempt in range(3):
        direct_click(JOB_ACT_BTN, "직업활동")
        t0 = time.time()
        while running and alive and time.time() - t0 < REOPEN_WAIT:
            if window_open(sct):
                print("음식만들기 창 열림 확인")
                time.sleep(random.uniform(1.0, 1.8))
                return True
            time.sleep(0.2)
        if not (running and alive):
            return False
        # 음식만들기가 안 떴음 — 직업 창이 사라졌으면 클릭은 먹었는데 뭔가 꼬인 것,
        # 남아있으면 클릭이 빗나간 것. 어느 쪽이든 직업 창부터 다시 확보하고 재시도.
        if win_visible("직업") is False:
            print("  직업활동은 눌렸는데 음식만들기 창이 안 뜸 → 직업 창부터 다시 열기")
            if not open_job_window():
                return False
        else:
            print("  직업활동 클릭이 안 먹은 듯 (직업 창 그대로) → 다시 클릭")
    print("[실패] 음식만들기 창이 안 열림 — 좌표/창 위치 확인")
    return False


def win_visible(title):
    """해당 제목의 게임 창이 화면에 보이는지. True/False, 확인 불가면 None.

    (이전 세션의 유령 창이 잡히는 걸 줄이려고 visible 여부까지 확인)
    """
    if _gw is None:
        return None
    try:
        for w in _gw.getAllWindows():
            if w.title == title and w.width > 0 and w.visible:
                return True
        return False
    except Exception:
        return None


def bag_open():
    """가방(아이템) 창이 보이는지. 확인 불가면 열려있다고 가정."""
    v = win_visible("아이템")
    return True if v is None else v


def open_bag():
    """가방 창이 안 보이면 한 번 열어봄. 열렸으면(또는 확인 불가면) True."""
    if bag_open():
        return True
    print("가방(아이템) 창이 안 보임 → 열기 시도")
    if BAG_KEY is not None:
        keyboard.send(BAG_KEY)
    elif BAG_BTN is not None:
        direct_click(BAG_BTN, "가방")
    else:
        print("[설정 필요] BAG_KEY(단축키) 또는 BAG_BTN(가방 아이콘 좌표)을 "
              "설정해야 자동으로 열 수 있음 — measure.py로 측정해서 입력")
        return False
    t0 = time.time()
    while running and alive and time.time() - t0 < BAG_WAIT:
        if bag_open():
            print("가방 창 열림 확인")
            time.sleep(random.uniform(0.8, 1.4))
            return True
        time.sleep(0.2)
    print("[실패] 가방 창이 안 열림")
    return False


def slot_filled(sct, slot_index):
    """요리창 재료 슬롯(0부터 셈)에 아이템이 실제로 들어있는지 확인.

    빈 슬롯은 어두운 검은 칸이라 밝은 픽셀이 거의 없음. 작은 영역 캡처
    한 장이면 끝나서(수 ms) 넣어도 체감 속도엔 영향 없음.
    """
    cx = int(SLOT1_CENTER[0] + slot_index * SLOT_PITCH_X)
    cy = int(SLOT1_CENTER[1])
    half = CELL_SIZE // 2
    shot = sct.grab({"left": cx - half, "top": cy - half,
                     "width": CELL_SIZE, "height": CELL_SIZE})
    img = np.asarray(shot, dtype=int)[:, :, :3]
    return int((img.sum(axis=2) > 90).sum()) >= MIN_SLOT_PX


def _scan_with_retries(sct, templates):
    """인벤토리를 최대 3번 스캔해서 레시피 재료가 다 잡히는 결과를 얻어봄."""
    found, min_diffs = {}, {}
    for attempt in range(3):
        found, min_diffs = scan_inventory(sct, templates)
        if all(name in found for name, _ in RECIPE):
            break
        time.sleep(random.uniform(0.2, 0.4))
    print("인벤토리 인식:", {k: len(v) for k, v in found.items()})
    return found, min_diffs


def fill_slots(sct, templates):
    """레시피대로 재료를 요리창 슬롯에 드래그. 성공하면 True.

    스캔은 매판 하지 않고 SCAN_EVERY판에 1번만 — 재료가 쌓여 있어 칸 배치가
    자주 안 바뀌기 때문. 사이 판들은 지난 스캔 결과를 재사용하고,
    재사용한 결과가 모자라 보이면 그 자리에서 즉시 다시 스캔해서 자가복구함.
    """
    global _scan_cache, _rounds_since_scan, _fail_detail
    min_diffs = {}
    if _scan_cache is not None and _rounds_since_scan < SCAN_EVERY:
        found = _scan_cache
        print(f"인벤토리 스캔 생략 — 지난 결과 재사용 ({_rounds_since_scan + 1}/{SCAN_EVERY}판째)")
    else:
        found, min_diffs = _scan_with_retries(sct, templates)
        _scan_cache, _rounds_since_scan = found, 0

    # 레시피에 필요한 개수만큼 칸이 잡혔는지 먼저 확인.
    need = {}
    for name, count in RECIPE:
        need[name] = need.get(name, 0) + count

    def lacking():
        return [n for n, c in need.items() if len(found.get(n, [])) < c]

    if lacking() and _rounds_since_scan > 0:
        # 캐시를 재사용 중이었음 → 낡았을 수 있으니 즉시 새로 스캔해서 다시 확인
        print("재사용한 스캔 결과가 부족함 → 즉시 다시 스캔")
        found, min_diffs = _scan_with_retries(sct, templates)
        _scan_cache, _rounds_since_scan = found, 0

    if lacking():
        _fail_detail = ", ".join(
            f"'{n}' 부족 (필요 {need[n]}개, 인식 {len(found.get(n, []))}개)" for n in lacking())
        for n in lacking():
            print(f"[중단] 재료 '{n}' 가 부족함 (필요 {need[n]}, 인식 {len(found.get(n, []))})")
            print(f"       가장 비슷한 칸의 차이값: {min_diffs.get(n, 0):.1f} "
                  f"(인식 기준: {threshold_for(n)} 이하)")
        try:
            save_debug_scan(sct)
        except Exception:
            pass
        _scan_cache = None   # 다음 시도 땐 무조건 새로 스캔
        return False

    # 드래그 계획: 슬롯 순서대로 어떤 재료가 들어가야 하는지
    plan = [name for name, count in RECIPE for _ in range(count)]
    if len(plan) > NUM_SLOTS:
        print(f"[중단] 레시피 재료 수({len(plan)})가 열려있는 슬롯({NUM_SLOTS}개)을 넘음")
        return False

    # 슬롯마다 반드시 한 번은 드래그함. (드래그 '전'에 slot_filled로 건너뛰던 로직은
    #  제거 — 빈 슬롯이 밝게 읽히는 자리(예: 5번째 칸 테두리)가 있으면 '이미 찼다'고
    #  오판해서 그 슬롯을 통째로 건너뛰는 버그가 있었음)
    used = {}
    for slot, name in enumerate(plan):
        dst = (SLOT1_CENTER[0] + slot * SLOT_PITCH_X, SLOT1_CENTER[1])
        placed = False
        # 드래그한 뒤 슬롯에 실제로 들어갔는지 확인. 안 들어갔으면(칸이 비었거나
        # 드래그 튕김) 같은 재료의 다른 칸으로 재시도.
        while running and alive and not placed:
            idx = used.get(name, 0)
            if idx >= len(found.get(name, [])):
                break                # 이 재료는 더 시도할 칸이 없음
            src = found[name][idx]
            used[name] = idx + 1
            print(f"'{name}' → 슬롯 {slot+1} 드래그")
            human_drag(src, dst)
            if slot_filled(sct, slot):
                placed = True
            else:
                print(f"  [재시도] 슬롯 {slot+1}에 안 들어감 → 다른 칸에서 다시")
        if not (running and alive):
            return False
        if not placed:
            _fail_detail = f"슬롯 {slot+1}에 '{name}' 를 넣지 못함 (칸 부족/드래그 실패)"
            print(f"[중단] 슬롯 {slot+1}에 '{name}' 를 넣지 못함")
            try:
                save_debug_scan(sct)
            except Exception:
                pass
            _scan_cache = None       # 다음 시도 땐 무조건 새로 스캔
            return False

    # 시작 전 최종 확인 — 슬롯이 전부 실제로 채워졌는지 (5개 다 들어갔나)
    empty = [i + 1 for i in range(len(plan)) if not slot_filled(sct, i)]
    if empty:
        _fail_detail = f"시작 직전 확인 — 슬롯 {empty} 이 비어 있음"
        print(f"[중단] 최종 확인 — 슬롯 {empty} 이 비어 있음 (시작 안 함)")
        _scan_cache = None
        return False
    print(f"재료 {len(plan)}개 전부 들어간 것 확인")
    _rounds_since_scan += 1
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
    last_dir = None        # 직전에 누른 방향 '+'/'-' — 연속 같은방향 누름 방지
    last_press = 0.0       # 직전에 누른 시각
    history = []           # (시각, 위치) — 속도 계산용

    def do_hold(sign):
        nonlocal last_dir, last_press
        if sign > 0:
            hold_toward(sct, PLUS_BTN, +1, "+"); last_dir = "+"
        else:
            hold_toward(sct, MINUS_BTN, -1, "-"); last_dir = "-"
        last_press = time.time()
        history.clear()    # 누른 뒤엔 속도 이력 리셋

    while running and alive:
        now = time.time()
        if now - t_start > COOK_TIMEOUT:
            print("\n[경고] 시간 초과 — 이번 판 종료 처리")
            return False

        # 시작을 눌렀는데 수은이 한 번도 안 보임 = 시작 자체가 실패
        # (슬롯이 비었거나 클릭이 빗나감) → 오래 기다리지 말고 일찍 접고 자가복구로
        if not seen and now - t_start > NO_MERCURY_SEC:
            print(f"\n[문제] 시작 후 {NO_MERCURY_SEC}초 동안 수은이 안 보임 — 시작 실패로 판단")
            return False

        # 창이 실제로 닫혔는지 매번 먼저 확인 (수은 색이 뭔가에 남아 있어도
        # 창이 닫혔으면 무조건 요리 끝으로 처리 — 오검출 방지의 핵심)
        if seen and now - t_start > MIN_ROUND_SEC and not window_open(sct):
            none_since = none_since or now
            if now - none_since > DONE_NONE_SEC:
                print("\n요리 끝 감지! (창 닫힘 확인)")
                return True
            time.sleep(SAMPLE_DT)
            continue
        none_since = None

        pos = read_pos(sct)

        if pos is None:
            # 창은 열려있는데 수은이 눈금 밖 = 너무 차갑거나 뜨거움 → 되돌리기
            want = "+" if last_pos >= ZONE_CENTER else "-"
            if want != last_dir or now - last_press > REPRESS_SEC:
                do_hold(+1 if want == "+" else -1)
            else:
                time.sleep(SAMPLE_DT)
            continue

        seen = True
        none_since = None
        last_pos = pos

        # 최근 이력으로 이동 속도 → 예측 위치(pred). "지금 위치"가 아니라 "곧 갈 위치"로 판단.
        history.append((now, pos))
        history[:] = [(t, p) for (t, p) in history if now - t <= VEL_WINDOW]
        v = (pos - history[0][1]) / max(now - history[0][0], 1e-3) if len(history) >= 2 else 0.0
        pred = pos + LOOKAHEAD * v

        # 예측이 구간을 벗어날 것 같으면, "실제로 벗어나기 전에" 미리 반대로 누름.
        #   pred가 구간 위(뜨거움, pred<ZONE_TOP) → 냉각(-)
        #   pred가 구간 아래(차가움, pred>ZONE_BOT) → 가열(+)
        #   pred가 구간 안 → 그냥 지켜봄 (관성으로 알아서 흐름)
        if pred > ZONE_BOT:
            want = "+"
        elif pred < ZONE_TOP:
            want = "-"
        else:
            print(f"pos {pos:.2f} v{v:+.2f} pred {pred:.2f} 적정", " " * 6, end="\r")
            last_dir = None
            time.sleep(SAMPLE_DT)
            continue

        # 방금 같은 방향을 눌렀으면 관성으로 넘어올 시간을 주고 기다림 (연속 누름 방지).
        if want == last_dir and now - last_press < REPRESS_SEC:
            print(f"pos {pos:.2f} pred {pred:.2f} {want}후 대기", " " * 6, end="\r")
            time.sleep(SAMPLE_DT)
            continue

        print(f"pos {pos:.2f} → {want} 꾹", " " * 12, end="\r")
        do_hold(+1 if want == "+" else -1)
    return False


# ---------------------------------------------------------------- 텔레그램 알림

# 일부 컴퓨터는 백신/보안 프로그램이 HTTPS를 중간 검사하면서 자체 인증서를
# 끼워넣어 파이썬의 인증서 검증이 실패함 (CERTIFICATE_VERIFY_FAILED).
# → truststore가 설치돼 있으면 윈도우 인증서 저장소를 그대로 써서 해결하고
#   (py -m pip install truststore 권장), 그래도 실패하면 알림 전송에 한해
#   검증 없이 보냄 (게임 알림이라 민감정보 없음. 다른 통신엔 영향 없음).
import ssl as _ssl
try:
    import truststore as _truststore
    _truststore.inject_into_ssl()
except Exception:
    pass
_tg_ctx = None   # None = 기본 검증. 검증 실패를 한 번 겪으면 무검증으로 전환


def _tg_urlopen(url_or_req, data=None, timeout=30):
    global _tg_ctx
    try:
        return urllib.request.urlopen(url_or_req, data=data, timeout=timeout,
                                      context=_tg_ctx)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        if _tg_ctx is None and isinstance(reason, _ssl.SSLCertVerificationError):
            print("  (텔레그램: 보안프로그램의 HTTPS 검사 감지 — 인증서 검증 생략 모드로 전환)")
            _tg_ctx = _ssl._create_unverified_context()
            return urllib.request.urlopen(url_or_req, data=data, timeout=timeout,
                                          context=_tg_ctx)
        raise


def _send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
    _tg_urlopen(url, data=data, timeout=10)


def _capture_screen_jpeg():
    """전체 화면(모든 모니터)을 JPEG 바이트로 캡처. 실패하면 None.

    notify는 백그라운드 스레드에서 도니까, 워커의 mss를 공유하지 않고
    이 함수 안에서 새 mss 인스턴스를 만들어 캡처함(스레드 안전).
    """
    try:
        import io
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[0])   # 0 = 모든 모니터 합친 가상 화면
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if img.width > SHOT_MAX_W:             # 너무 넓으면 축소 (용량/전송속도)
            ratio = SHOT_MAX_W / img.width
            img = img.resize((SHOT_MAX_W, max(1, int(img.height * ratio))))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception as e:
        print(f"  (스크린샷 캡처 실패: {e})")
        return None


def _send_telegram_photo(caption, jpeg_bytes):
    """스크린샷 1장을 캡션과 함께 텔레그램으로 전송 (multipart/form-data 직접 구성)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    boundary = "----cookbot" + str(random.randint(10 ** 9, 10 ** 10))
    def field(name, value):
        return (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n").encode()
    body = b"".join([
        field("chat_id", TELEGRAM_CHAT_ID),
        field("caption", caption[:1024]),      # 텔레그램 캡션 최대 1024자
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="photo"; filename="screen.jpg"\r\n',
        b"Content-Type: image/jpeg\r\n\r\n",
        jpeg_bytes, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    _tg_urlopen(req, timeout=30)


def notify(text, key=None, wait=False, photo=False):
    """봇 상태를 텔레그램으로 알림. 토큰/chat_id가 비어있으면 조용히 넘어감.

    - key가 같은 알림은 NOTIFY_COOLDOWN 안엔 다시 안 보냄 (같은 오류 도배 방지)
    - 기본은 백그라운드 스레드로 전송 → 인터넷이 느려도 봇 동작에 영향 없음
    - wait=True는 프로그램이 곧 종료되는 경우용 (전송이 끝날 때까지 기다림)
    - photo=True면 화면 스크린샷을 캡션과 함께 보냄 (실패 시 글자만이라도 보냄)
    """
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return
    now = time.time()
    k = key or text
    if now - _last_notify.get(k, 0) < NOTIFY_COOLDOWN:
        return
    _last_notify[k] = now

    def _send():
        label = f"[{NOTIFY_NAME}] {text}"
        try:
            if photo and SEND_SCREENSHOT:
                shot = _capture_screen_jpeg()
                if shot is not None:
                    _send_telegram_photo(label, shot)
                    print("  (텔레그램 알림+스크린샷 보냄)")
                    return
            _send_telegram(label)                # 사진 안 쓰거나 캡처 실패 → 글자만
            print("  (텔레그램 알림 보냄)")
        except Exception as e:
            print(f"  (텔레그램 알림 실패: {e})")

    if wait:
        _send()
    else:
        threading.Thread(target=_send, daemon=True).start()


def maybe_report():
    """REPORT_EVERY_MIN 간격으로 누적 완료 판수를 현황 보고. 정지 중엔 안 보냄."""
    global _last_report, _rounds_at_report
    if not REPORT_EVERY_MIN:
        return
    now = time.time()
    if now - _last_report < REPORT_EVERY_MIN * 60:
        return
    _last_report = now
    if not (running or retry_at is not None):
        return   # 사용자가 직접 꺼둔 상태 — 보고 생략 (타이머만 갱신)
    recent = _rounds_done - _rounds_at_report
    _rounds_at_report = _rounds_done
    up = int((now - _session_t0) / 60)
    state = "실행 중" if running else "오류 후 재시작 대기 중"
    notify(f"📊 현황: 가동 {up // 60}시간 {up % 60}분 · 누적 {_rounds_done}판 완료 "
           f"(최근 {REPORT_EVERY_MIN}분간 {recent}판) · 상태: {state}", key="status", photo=True)


# ---------------------------------------------------------------- 메인 루프

def stop_with_retry(reason):
    """오류로 멈출 때 호출 — RETRY_SEC 뒤 자동으로 F8을 누른 것처럼 재시작 예약.

    사용자가 이미 F8로 끈 상태(running=False)면 아무것도 안 함 —
    사용자의 정지 의사를 자동 재시작이 덮어쓰지 않게.
    """
    global running, retry_at, _fail_detail
    if not running:
        return
    running = False
    detail = _fail_detail
    _fail_detail = ""
    msg = reason + (f"\n상세: {detail}" if detail else "")
    tally = f"\n(지금까지 누적 {_rounds_done}판 완료)"
    if RETRY_SEC is not None:
        retry_at = time.time() + RETRY_SEC
        print(f"[정지] {reason} — {RETRY_SEC}초 뒤 자동 재시작 (즉시 재개 F8, 종료 F9)")
        notify(f"⚠ 멈춤: {msg}\n({RETRY_SEC}초 뒤 자동 재시작을 시도합니다){tally}",
               key=reason, photo=True)
    else:
        print(f"[정지] {reason}")
        notify(f"⚠ 멈춤: {msg}{tally}", key=reason, photo=True)


def checkup(sct):
    """오류가 났을 때 스스로 상태를 점검하고, 고칠 수 있는 건 그 자리에서 고침.

    점검 순서:
      1. 혹시 마우스 버튼을 누른 채면 뗌
      2. 창 위치 재보정 (창이 밀렸을 수 있음)
      3. 음식만들기 창이 닫혔으면 다시 열기 (직업 → 직업활동)
      4. 가방(아이템) 창이 안 보이면 열기
      5. 인벤토리 스캔 캐시를 비워서 다음 시도 땐 무조건 새로 스캔
    """
    global _scan_cache
    print("  [자가점검] 상태 확인 중...")
    try:
        pyautogui.mouseUp()
    except Exception:
        pass
    recalibrate("all")
    ok = True
    if not window_open(sct):
        print("  [자가점검] 음식만들기 창이 닫혀있음 → 다시 열기")
        ok = reopen_window(sct) and ok
    if not bag_open():
        print("  [자가점검] 가방(아이템) 창이 안 보임 → 열기")
        ok = open_bag() and ok
    _scan_cache = None
    print("  [자가점검] 완료 — 곧바로 재시도" if ok else "  [자가점검] 일부 복구 실패")
    return ok


def step_failed(sct, reason):
    """어느 단계든 실패하면 호출 — 자가점검으로 고치고 곧바로 재시도.

    연속으로 MAX_FIX_TRIES번 실패하면 그때는 stop_with_retry로 넘어가
    RETRY_SEC 대기 후 자동 재시작. 사용자가 F8로 끈 경우엔 아무것도 안 함.
    """
    global _fail_streak
    if not (running and alive):
        return
    _fail_streak += 1
    print(f"[문제] {reason} (연속 {_fail_streak}/{MAX_FIX_TRIES}번째)")
    if _fail_streak >= MAX_FIX_TRIES:
        _fail_streak = 0
        stop_with_retry(f"{reason} — 자가복구 {MAX_FIX_TRIES}번 실패")
        return
    checkup(sct)
    time.sleep(random.uniform(0.8, 1.5))


def run_round(sct, templates):
    """한 판 진행: 창/가방 확인 → 재료 넣기 → 요리.

    어느 단계든 실패하면 step_failed가 자가점검 후 즉시 재시도하고,
    연속 실패가 쌓이면 그때만 RETRY_SEC 대기 후 자동 재시작으로 넘어감.
    """
    global running, _fail_streak, _rounds_done

    if CELL1_CENTER == (0, 0) or SLOT1_CENTER == (0, 0):
        print("[설정 필요] CELL1_CENTER / SLOT1_CENTER 좌표를 측정해서 넣어주세요.")
        running = False   # 설정 문제는 재시도해도 소용없음 → 자동 재시작 안 함
        return

    # 창을 옮겼어도 따라가도록 현재 창 위치로 좌표 보정
    recalibrate("all")

    # 요리창이 닫혀있으면 (직업 → 직업활동으로) 다시 열기
    if not window_open(sct):
        print("음식만들기 창이 닫혀있음 → 다시 열기")
        if not reopen_window(sct):
            step_failed(sct, "음식만들기 창을 열지 못함")
            return

    # 가방(아이템) 창이 안 보이면 자동으로 한 번 열기 (닫혀있으면 재료 인식 불가)
    if not open_bag():
        step_failed(sct, "가방(아이템) 창을 열지 못함")
        return

    # 재료 넣기 직전, 인벤토리/요리창 위치 다시 보정
    recalibrate("cook")
    recalibrate("item")
    if not fill_slots(sct, templates):
        step_failed(sct, "재료 넣기 실패")
        return
    if not cook_one_round(sct):
        step_failed(sct, "요리가 정상 종료되지 않음")
        return

    _fail_streak = 0   # 한 판 성공 → 연속 실패 카운트 리셋
    _rounds_done += 1
    print(f"★ 한 판 완료! (누적 {_rounds_done}판)")
    if not LOOP:
        running = False
        print("정지 (LOOP=False). 다시 하려면 F8.")
    else:
        # 판 사이 휴식 — 마우스를 잠깐 배회시킨 뒤 쉼
        idle_wander()
        time.sleep(random.uniform(1.0, 2.0))


def worker():
    global running, alive, retry_at
    try:
        templates = load_templates()
        # items 폴더엔 다른 요리용 재료 아이콘도 섞여있을 수 있는데, 지금 RECIPE에
        # 없는 재료는 매칭될 일이 없으니 미리 걸러냄 — 등록된 아이콘 수가 많을수록
        # (칸마다 비교해야 할 템플릿이 늘어) 스캔이 느려지므로 이렇게 줄이는 게 이득
        recipe_names = {name for name, _ in RECIPE}
        templates = {k: v for k, v in templates.items() if k in recipe_names}
        if not templates:
            print("[주의] items 폴더에 RECIPE 재료 아이콘이 없음 — capture_items.py부터 실행")
        else:
            print("등록된 재료:", ", ".join(templates))
            missing = recipe_names - templates.keys()
            if missing:
                print(f"[주의] RECIPE에 있지만 아이콘이 없는 재료: {', '.join(missing)}")
        if WINDOW_FOLLOW:
            print("창 자동 추적 ON — 게임 창(음식만들기/아이템/직업)을 옮겨도 따라감")
        else:
            print("창 자동 추적 OFF — 창을 측정한 자리에 고정해야 함 "
                  "(pygetwindow 설치 시 자동 ON)")

        with mss.mss() as sct:
            while alive:
                maybe_report()   # 주기 현황 보고 (때가 됐을 때만 전송)
                if not running:
                    # 오류로 멈춘 뒤 예약된 시각이 지나면 자동 재시작 (강제 F8)
                    if retry_at is not None and time.time() >= retry_at:
                        retry_at = None
                        running = True
                        print("\n⏰ 자동 재시작! (오류 후 대기시간 경과)")
                    else:
                        time.sleep(0.1)
                    continue

                retry_at = None
                try:
                    run_round(sct, templates)
                except pyautogui.FailSafeException:
                    raise
                except Exception:
                    import traceback
                    print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
                    traceback.print_exc()
                    try:
                        step_failed(sct, "에러 발생")   # 자가점검 후 곧바로 재시도
                    except Exception:
                        stop_with_retry("에러 발생 (자가점검도 실패)")
    except pyautogui.FailSafeException:
        print("\n\n[비상정지] 마우스가 화면 구석으로 이동해서 안전정지 됐어요.")
        print("       보통 이 컴퓨터의 화면 해상도/창 위치가 좌표를 측정했던")
        print("       컴퓨터와 달라서, 추적 안 되는 좌표(JOB_BTN 등)가 화면")
        print("       밖으로 나갔을 때 발생해요. measure.py로 이 컴퓨터에서")
        print("       해당 좌표를 다시 재서 코드 상단 값을 바꿔주세요.")
        notify(f"🛑 비상정지(마우스가 화면 구석) — 봇이 완전히 종료됨. 직접 다시 실행해야 함."
               f"\n(지금까지 누적 {_rounds_done}판 완료)", wait=True, photo=True)
        alive = False
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        notify(f"🛑 치명적 에러로 봇이 완전히 종료됨. 컴퓨터에서 콘솔 확인 필요."
               f"\n(지금까지 누적 {_rounds_done}판 완료)", wait=True, photo=True)
        alive = False


def toggle():
    global running, retry_at, _fail_streak, _scan_cache
    retry_at = None      # 사용자가 직접 F8을 누르면 예약된 자동 재시작은 취소
    _fail_streak = 0
    _scan_cache = None   # 사용자가 손댔을 수 있으니 다음 판은 새로 스캔
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
