# -*- coding: utf-8 -*-
"""
의장이(재봉틀) 자동 — 재료 넣기 → 시작 → 박음질 → 반복.

■ 게임 (영상으로 확인한 것)
  - 회색 천에 세로 칸이 5개. 칸마다 노란 띠(왼박음) 자리와 파란 띠(오른박음) 자리가 있음
  - 띠는 위에서 일정한 간격(0.4~0.5초)마다 한 줄씩 내려옴 — 간격은 봇이 화면으로 잼
  - 바늘 두 개는 마우스 좌우 위치를 따라 칸 단위로 움직임
  - 띠가 빨간 실선(바늘)에 걸쳐 있는 동안 그 색 키를 누르고 있으면 점수가 오름
  - 띠가 없는데 누르고 있으면 빨간 실이 나오고 점수가 깎임
  - 250점이 되면 창이 사라지고 끝 (못 채우면 재료만 없어짐)

■ 이 봇이 하는 일
  - 내려오는 띠를 줄 단위로 기억하고, 줄이 내려가는 순간과 간격을 화면으로 정확히 맞춤
  - 띠가 바늘에 닿는 순간 바로 뒤에 누르고, 띠가 끝나는 순간 바로 앞에 뗌
  - 앞으로 10초 동안 가장 많이 박을 수 있는 칸 순서를 계산해서 마우스를 미리 옮김
  - 점수 막대를 계속 보면서, 점수가 깎이면 바로 떼고 타이밍을 스스로 맞춤

■ 처음 한 번
  1. py measure_sew.py              (창 위치 재기 — F1)
  2. 제작 창을 띄우고  py auto_match.py 캡처  → items 폴더의 재료 그림 이름 바꾸기
  3. 아래 RECIPE 에 재료 이름과 개수 적기
■ 실행:  py auto_sew.py   →  F8 시작/정지,  F9 종료
"""

import os
import sys
import time
import random
import threading
from collections import deque

try:
    import numpy as np
    import mss
    import pyautogui
    import keyboard
except ImportError as e:
    print("[에러] 필요한 프로그램이 없습니다:", e)
    print("cmd 에서:  py -m pip install mss numpy pyautogui keyboard pillow pygetwindow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auto_match as am        # 제작 창 열기 / 재료 넣기 / 창 찾기는 주장이 봇 것을 그대로 씀

# ==================== 설정 ====================
RECIPE = [("재료1", 1), ("재료2", 1), ("재료3", 1)]   # ← 재료 이름(items 폴더 그림 이름)과 개수
NUM_SLOTS = 3                       # 제작 창 재료 칸 수
LEFT_KEY = ","                      # 왼박음(노랑) = 키보드 < 키 (Shift 없이)
RIGHT_KEY = "."                     # 오른박음(파랑) = 키보드 > 키 (Shift 없이)
MAX_GAMES = 0                       # 이만큼 하면 멈춤 (0 = 재료 떨어질 때까지 계속)
GAME_TIMEOUT = 180                  # 한 판 최대 시간(초). 보통은 그 전에 창이 사라짐

# 박음질 타이밍 (띠가 한 줄 내려가는 순간 = '틱', 0.5초마다)
PRESS_AFTER = 0.03                  # 띠가 바늘에 닿는 틱보다 이만큼(초) 늦게 누름 (일찍 누르면 빨간 실)
RELEASE_BEFORE = 0.08               # 띠가 끝나는 틱보다 이만큼(초) 먼저 뗌 (늦게 떼면 빨간 실)
TIMING_JITTER = 0.015               # 누르고 떼는 시점을 매번 이만큼 안에서 살짝 다르게 (사람처럼)
KEY_REPEAT_DELAY = 0.5              # 꾹 누를 때 윈도우 자동 반복 흉내 (처음 누른 뒤 반복 시작까지)
KEY_REPEAT_EVERY = 0.033            #   반복 간격
MOVE_TIME = (0.08, 0.20)            # 바늘을 옮길 때 마우스 이동 시간(초): 옆 칸 ~ 끝에서 끝
LOOP_DT = 0.004                     # 화면 보는 간격(초)
DEBUG = False                       # True 면 게임 중 상태를 자주 찍음
SAVE_DEBUG_SHOT = True              # 판 시작 때 화면 인식 결과를 sew_debug.png 로 저장 (문제 생기면 보내주세요)
DUMP_GAMES = 2                      # 켠 뒤 처음 이만큼 판은 한 판 전체 화면/기록을 sew_frames 폴더에 저장
                                    # (분석용 — 폴더를 압축해서 보내주면 띠를 왜 놓쳤는지 볼 수 있음. 다 되면 0)

# 사람처럼 쉬기 (판과 판 사이에만 쉼. REST = False 면 안 쉼)
REST = False                        # 의장이는 쉬지 않고 계속 (True 로 바꾸면 아래 설정대로 쉼)
BREATH_SECS = (1.5, 5)              # 판 끝나고 다음 판까지 잠깐
SHORT_EVERY = (1, 5)                # 짧은 쉼: 이 판수마다 한 번
SHORT_SECS = (10, 60)               #   쉬는 시간(초)
SESSION_MINS = (40, 90)             # 한 번 앉아서 하는 시간(분) → 끝나면 자리 비움
BREAK_MINS = (10, 25)               #   자리 비움 시간(분) — 제작 창을 닫고 쉼
BIG_EVERY_HOURS = (3, 4)            # 이만큼마다 한 번은 크게 쉼
BIG_MINS = (40, 90)                 #   크게 쉬는 시간(분)
FAIL_WAIT = 60                      # 재료 넣기 등이 실패하면 이만큼 기다렸다 다시
FAIL_STOP = 5                       # 연속 이만큼 실패하면 멈춤

running = False
alive = True

# ----- 영상에서 잰 게임 안 배치 (회색 천 상자 왼쪽 위 기준, 천 폭 379 일 때 픽셀) -----
REF_W = 379.0                       # 회색 천 폭
REF_YCOL0, REF_BCOL0 = 20.0, 57.0   # 1번 칸 노란 띠 / 파란 띠 가운데 x
REF_STEP = 75.0                     # 칸 간격
REF_CLIP = 5.0                      # 띠가 처음 나타나는 높이 (0번 줄 위쪽)
REF_ROW = 7.5                       # 한 줄 높이 (0.5초마다 이만큼 내려옴)
REF_LINE_ROWS = 21.87               # 빨간 실선 높이 (줄 단위) — 화면에서 못 찾을 때만 씀
REF_NEEDLE_Y = (143.0, 162.0)       # 바늘 흰 몸통이 있는 높이
REF_NEEDLE_X = 44.7                 # 바늘 흰 부분 평균 x (1번 칸일 때)
REF_BAR = (107.0, 354.0, 331.0, 339.0)  # 점수 막대: 0점 x, 250점 x, 읽을 높이 위·아래
REF_MOUSE_Y = 205.0                 # 마우스를 둘 높이 (빨간 실선 아래 천)
REF_BTN_Y = (414.0, 444.0)          # 왼박음/오른박음 버튼 (누르면 청록색) — 게임이 키를 받은 걸 화면으로 확인
REF_BTN_X = ((79.0, 160.0), (219.0, 300.0))
HIT_ROW = 21                        # 띠가 위에서 21번 줄(0부터)에 있을 때 박음질이 됨
SEE_ROWS = 18                       # 0~17번 줄만 봄 (그 아래는 바늘에 가려질 수 있음)
NCOL = 10                           # 띠 자리 10개 (칸 k: 노랑 2k, 파랑 2k+1)
OFF = 700                           # 줄 기억 배열에서 0번의 위치


# ==================== 공통 ====================

def shot(sct, left, top, w, h):
    s = sct.grab({"left": int(left), "top": int(top), "width": int(w), "height": int(h)})
    return np.asarray(s)[:, :, :3].astype(np.int16)


def window_shown(w):
    try:
        return am._really_shown(w)
    except Exception:
        return False


def find_game_win(ignore=()):
    ws = am.find_windows("card", ignore=ignore)
    return ws[0] if ws else None


class Keys:
    """왼박음/오른박음 키를 꾹 누르기/떼기 (꾹 누를 때 윈도우 자동 반복도 흉내)."""

    def __init__(self):
        self.down = {LEFT_KEY: None, RIGHT_KEY: None}     # 누른 시각 (안 누름 = None)
        self.rep = {LEFT_KEY: 0.0, RIGHT_KEY: 0.0}
        self.presses = 0
        self.log = []                                    # (시각, 키, 누름 True / 뗌 False)

    def set(self, key, on, now):
        if on and self.down[key] is None:
            keyboard.press(key)
            self.down[key] = now
            self.rep[key] = now + KEY_REPEAT_DELAY
            self.presses += 1
            self.log.append((now, key, True))
        elif not on and self.down[key] is not None:
            keyboard.release(key)
            self.down[key] = None
            self.log.append((now, key, False))

    def tick(self, now):
        for k, t in self.down.items():
            if t is not None and now >= self.rep[k]:
                keyboard.press(k)                         # 꾹 누르고 있을 때의 자동 반복 신호
                self.rep[k] = now + KEY_REPEAT_EVERY

    def held(self):
        return [k for k, t in self.down.items() if t is not None]

    def release_all(self):
        now = time.time()
        for k in list(self.down):
            if self.down[k] is not None:
                try:
                    keyboard.release(k)
                except Exception:
                    pass
                self.log.append((now, k, False))
            self.down[k] = None


class Mover:
    """마우스를 기다리지 않고(non-blocking) 조금씩 옮김 — 옮기는 동안에도 화면을 계속 봄."""

    def __init__(self):
        self.job = None

    def go(self, x, y, now, lanes=1):
        mx, my = pyautogui.position()
        if abs(x - mx) + abs(y - my) < 2:
            self.job = None
            return
        lo, hi = MOVE_TIME
        dur = (lo + (hi - lo) * min(1.0, (lanes - 1) / 3.0)) * random.uniform(0.85, 1.15)
        bow = random.uniform(-1, 1) * min(10.0, abs(x - mx) * 0.06)
        self.job = (mx, my, x, y, now, dur, bow)

    def busy(self):
        return self.job is not None

    def step(self, now):
        if self.job is None:
            return
        sx, sy, x, y, t0, dur, bow = self.job
        t = min(1.0, (now - t0) / dur)
        e = t * t * (3 - 2 * t)
        pyautogui.moveTo(int(round(sx + (x - sx) * e)),
                         int(round(sy + (y - sy) * e + bow * 4 * e * (1 - e))))
        if t >= 1.0:
            self.job = None


# ==================== 게임 화면 읽기 ====================

def find_fabric(img):
    """의장이 창 화면에서 회색 천(띠가 내려오는 곳)의 상자 (L, T, R, B). 못 찾으면 None."""
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    mx = np.maximum(np.maximum(b, g), r)
    mn = np.minimum(np.minimum(b, g), r)
    gray = (mx - mn < 26) & (mn > 100) & (mx < 215)
    h, w = gray.shape
    rows = gray.mean(axis=1) > 0.35
    gap_max = max(4, int(h * 0.04))             # 빨간 실선 때문에 끊긴 곳은 이어 붙임
    best, y = None, 0
    while y < h:
        if not rows[y]:
            y += 1
            continue
        s = last = y
        while y < h and y - last <= gap_max:
            if rows[y]:
                last = y
            y += 1
        if best is None or last + 1 - s > best[1] - best[0]:
            best = (s, last + 1)
    if best is None:
        return None
    T, B = best
    cols = np.nonzero(gray[T:B].mean(axis=0) > 0.5)[0]
    if len(cols) < 20:
        return None
    L, R = int(cols.min()), int(cols.max()) + 1
    if R - L < 0.45 * w or not 0.58 < (B - T) / (R - L) < 0.76:
        return None
    return float(L), float(T), float(R), float(B)


def find_line(img, L, R, ya, yb):
    """빨간 실선(바늘이 박는 가로줄)의 가운데 높이."""
    ya, yb = max(0, int(ya)), min(img.shape[0], int(yb))
    reg = img[ya:yb, int(L) + 2:int(R) - 2]
    if reg.size == 0:
        return None
    b, g, r = reg[..., 0], reg[..., 1], reg[..., 2]
    red = (r > 110) & (r > g + 60) & (r > b + 60)
    rows = np.nonzero(red.mean(axis=1) > 0.6)[0]
    if len(rows) == 0:
        return None
    return ya + float(rows.mean()) + 0.5


class Geo:
    """천 상자 하나로 정해지는 게임 안 좌표 (창을 찍은 그림 기준)."""

    def __init__(self, box, line=None):
        L, T, R, B = box
        s = (R - L) / REF_W
        self.box, self.L, self.T, self.R, self.B, self.s = box, L, T, R, B, s
        self.rh = REF_ROW * s
        self.clip = T + REF_CLIP * s
        self.line_found = line is not None
        self.line = line if line is not None else self.clip + REF_LINE_ROWS * self.rh
        hit = int(np.floor((self.line - self.clip) / self.rh - 0.45))
        self.hit = hit if HIT_ROW - 2 <= hit <= HIT_ROW + 2 else HIT_ROW
        self.ya = int(np.floor(self.clip))
        r0, r1 = [], []
        for r in range(SEE_ROWS):
            a = int(round(self.clip + (r + 0.25) * self.rh)) - self.ya
            b = max(a + 1, int(round(self.clip + (r + 0.75) * self.rh)) - self.ya)
            r0.append(a)
            r1.append(b)
        self.r0, self.r1 = np.array(r0), np.array(r1)
        self.yb = self.ya + int(self.r1.max()) + 1
        self.set_x(L - 0.25 * s, s)
        self.ny = (int(round(T + REF_NEEDLE_Y[0] * s)), int(round(T + REF_NEEDLE_Y[1] * s)) + 1)
        self.bar = (L + REF_BAR[0] * s, L + REF_BAR[1] * s,
                    int(round(T + REF_BAR[2] * s)), int(round(T + REF_BAR[3] * s)) + 1)
        self.mouse_y = T + REF_MOUSE_Y * s
        self.by = (int(round(T + REF_BTN_Y[0] * s)), int(round(T + REF_BTN_Y[1] * s)) + 1)
        self.bx = [(int(round(L + a * s)), int(round(L + b * s)) + 1) for a, b in REF_BTN_X]
        # 게임 중에 찍을 범위 (천 + 점수 막대 + 버튼)
        self.crop = (max(0, int(L) - 4), max(0, int(T) - 4), int(np.ceil(R)) + 4, self.by[1] + 4)

    def set_x(self, xa, xs):
        """띠 자리 가로 위치: 화면 x = xa + xs * (영상 기준 x).  처음엔 천 상자로 정하고,
        게임 중에 실제로 보이는 띠 위치로 다시 맞춤 (창 크기/배율이 달라도 5번째 칸까지 정확히)."""
        self.xa, self.xs = xa, xs
        hw = max(1, int(round(3.0 * self.s)))
        self.cx = []
        for k in range(5):
            for c0 in (REF_YCOL0, REF_BCOL0):
                x = int(round(xa + (c0 + REF_STEP * k) * xs))
                self.cx.append((x - hw, x + hw + 1))
        self.need = [0.4 * (self.r1 - self.r0) * (x1 - x0) for (x0, x1) in self.cx]

    def col_x(self, i):
        """띠 자리 i 의 가운데 x."""
        return self.xa + ((REF_YCOL0, REF_BCOL0)[i % 2] + REF_STEP * (i // 2)) * self.xs

    def moved(self, dx, dy):
        """좌표 기준을 옮긴 Geo (잘라 찍은 그림용)."""
        L, T, R, B = self.box
        g = Geo((L - dx, T - dy, R - dx, B - dy), self.line - dy)
        g.hit, g.line_found = self.hit, self.line_found
        g.set_x(self.xa - dx, self.xs)
        return g

    def lane_x(self, k):
        return self.xa + ((REF_YCOL0 + REF_BCOL0) / 2 + REF_STEP * k) * self.xs

    def lanes_visible(self, img):
        """칸마다 천이 화면에 보이는지 (다른 창에 가려졌으면 False) — 천 위쪽과 바늘 높이를 봄."""
        out = []
        b, g, r = img[..., 0], img[..., 1], img[..., 2]
        mx = np.maximum(np.maximum(b, g), r)
        mn = np.minimum(np.minimum(b, g), r)
        cloth = ((mx - mn < 26) & (mn > 100) & (mx < 215)) | (mn > 215)          # 회색 천 / 흰 바늘
        cloth |= (r > 140) & (g > b + 60) & (b < 130)                            # 노란 띠
        cloth |= (b > r + 60) & (b > g + 20) & (b > 90)                          # 파란 띠
        cloth |= (r > 110) & (r > g + 60) & (r > b + 60)                         # 빨간 실선
        y0, y1 = int(self.T + 4 * self.s), int(self.ny[1])
        for k in range(5):
            x0 = int(self.xa + (REF_STEP * k + 6) * self.xs)
            x1 = int(self.xa + (REF_STEP * (k + 1) - 6) * self.xs)
            reg = cloth[max(0, y0):y1, max(0, x0):x1]
            out.append(bool(reg.size) and reg.mean() > 0.6)
        return out

    def occupancy(self, img):
        """10개 띠 자리 x 18줄 — (띠 색이 있으면 True, 그 칸이 화면에 보이면 True).

        다른 창에 가려진 칸은 '보이지 않음' 으로 따로 알려줌 → 띠 기억을 지우지 않음.
        """
        occ = np.zeros((NCOL, SEE_ROWS), bool)
        vis = np.ones((NCOL, SEE_ROWS), bool)
        for i, (x0, x1) in enumerate(self.cx):
            sub = img[self.ya:self.yb, x0:x1]
            b, g, r = sub[..., 0], sub[..., 1], sub[..., 2]
            if i % 2 == 0:
                m = (r > 140) & (g > b + 60) & (r >= g - 10) & (b < 130)
            else:
                m = (b > r + 60) & (b > g + 20) & (b > 90)
            cs = np.concatenate(([0], np.cumsum(m.sum(axis=1))))
            occ[i] = (cs[self.r1] - cs[self.r0]) >= self.need[i]
            mx = np.maximum(np.maximum(b, g), r)
            mn = np.minimum(np.minimum(b, g), r)
            seen = m | ((mx - mn < 26) & (mn > 100)) | (mn > 200)        # 띠 / 회색 천 / 흰 바늘
            cv = np.concatenate(([0], np.cumsum(seen.sum(axis=1))))
            vis[i] = (cv[self.r1] - cv[self.r0]) >= 1.5 * self.need[i]
        return occ, vis

    def fabric_ok(self, img):
        """찍은 그림이 아직 천인지 (창이 사라지면 다른 화면이 찍힘)."""
        reg = img[int(self.T) + 2:int(self.line) - 6:6, int(self.L) + 2:int(self.R) - 2:6]
        b, g, r = reg[..., 0], reg[..., 1], reg[..., 2]
        mx = np.maximum(np.maximum(b, g), r)
        mn = np.minimum(np.minimum(b, g), r)
        return ((mx - mn < 26) & (mn > 100) & (mx < 215)).mean() > 0.55

    def buttons(self, img):
        """[왼박음 눌림?, 오른박음 눌림?] — 버튼이 청록색이면 게임이 키를 받은 것. 모르면 None."""
        out = []
        for x0, x1 in self.bx:
            reg = img[self.by[0]:self.by[1], x0:x1]
            if reg.size == 0:
                out.append(None)
                continue
            b, g, r = reg.reshape(-1, 3).mean(axis=0)
            if g - r > 35 and b - r > 40:
                out.append(True)
            elif abs(g - r) < 20 and abs(b - r) < 20:
                out.append(False)
            else:
                out.append(None)
        return out

    def needle_lane(self, img):
        """바늘이 있는 칸 (0~4). 못 찾으면 None."""
        band = img[self.ny[0]:self.ny[1], int(self.L):int(self.R)]
        ys, xs = np.nonzero(band.min(axis=2) > 215)
        if len(xs) < max(6, 12 * self.s * self.s):
            return None
        v = (xs.mean() + int(self.L) - self.xa - REF_NEEDLE_X * self.xs) / (REF_STEP * self.xs)
        k = int(round(v))
        if abs(v - k) > 0.45 or not 0 <= k <= 4:
            return None
        return k

    def read_score(self, img):
        """점수 막대 → 점수(0~250). 막대가 안 보이면 None."""
        x0, x1, y0, y1 = self.bar
        xa, xb = int(x0) - 2, int(np.ceil(x1)) + 2
        band = img[y0:y1, xa:xb]
        if band.shape[0] == 0 or band.shape[1] < 10:
            return None
        b, g, r = band[..., 0], band[..., 1], band[..., 2]
        cf = ((r > 90) & (r > g - 15) & (b < r - 40)).mean(axis=0)
        ce = ((g > r + 25) & (g > 70)).mean(axis=0)
        if ((cf > 0.5) | (ce > 0.5)).mean() < 0.7:
            return None
        xs = np.nonzero(cf > 0.5)[0]
        if len(xs) == 0:
            return 0.0
        end = xa + xs.max() + 1
        return max(0.0, min(250.0, (end - x0) / (x1 - x0) * 250.0))


def detect_geo(img):
    box = find_fabric(img)
    if box is None:
        return None
    L, T, R, B = box
    s = (R - L) / REF_W
    line = find_line(img, L, R, T + 150 * s, T + 190 * s)
    return Geo(box, line)


def geo_from_layout(w):
    """화면에서 천을 못 찾으면 measure_sew.py 로 잰 모서리를 씀."""
    pts = am._layout["points"]
    if "fab_tl" not in pts or "fab_br" not in pts:
        return None
    a = am.layout_point("fab_tl", w)
    b = am.layout_point("fab_br", w)
    box = (a[0] - w.left, a[1] - w.top, b[0] - w.left, b[1] - w.top)
    if box[2] - box[0] < 50:
        return None
    line = None
    if "line" in pts:
        line = am.layout_point("line", w)[1] - w.top
    return Geo(box, line)


def save_debug(img, geo, path):
    """인식 결과를 그림으로 저장 (천 상자, 띠 자리, 박음질 줄, 바늘/점수 읽는 곳)."""
    try:
        from PIL import Image, ImageDraw
        rgb = img[:, :, ::-1].clip(0, 255).astype(np.uint8)
        im = Image.fromarray(rgb)
        d = ImageDraw.Draw(im)
        L, T, R, B = geo.box
        d.rectangle([L, T, R - 1, B - 1], outline=(0, 255, 0))
        for i, (x0, x1) in enumerate(geo.cx):
            col = (255, 220, 0) if i % 2 == 0 else (0, 140, 255)
            d.rectangle([x0, geo.ya, x1 - 1, geo.yb], outline=col)
        y = geo.clip + geo.hit * geo.rh
        d.rectangle([L, y, R - 1, y + geo.rh], outline=(255, 0, 255))
        d.rectangle([L, geo.ny[0], R - 1, geo.ny[1]], outline=(255, 255, 255))
        x0, x1, y0, y1 = geo.bar
        d.rectangle([x0, y0, x1, y1], outline=(255, 0, 0))
        im.save(path)
    except Exception as e:
        print(f"  (sew_debug.png 저장 실패: {e})")


# ==================== 띠 기억 + 틱 시각 맞추기 ====================

class Tracker:
    """줄 단위로 띠를 기억하고, 띠가 내려가는 순간(틱)의 시각을 화면 변화로 맞춤.

    cells[i, a] : 띠 자리 i 의 '절대 칸' a 에 띠가 있는지 (1/0, 모름 -1).
                  틱 번호가 k 일 때 절대 칸 a 는 화면의 a+k 번 줄에 있음.
    """

    def __init__(self, hit, P=None):
        self.A = hit               # 띠 아래끝이 이 줄에 오면 박음질 시작
        self.D = hit               # 띠 위끝이 이 줄을 지나면 박음질 끝
        self.cells = np.full((NCOL, 2 * OFF), -1, np.int8)
        self.hist = deque(maxlen=4)
        self.events = []           # (틱 번호, 그 전 화면 시각, 그 후 화면 시각)
        self.phi = None            # 0번 틱 시각
        self.P = P or 0.5
        self.P_known = P is not None   # 지난 판에서 잰 간격 → 첫 틱 하나로 바로 시각을 맞춤
        self.misfit = 0
        self.k0 = 0                # phi 를 모를 때 쓰는 틱 번호
        self.outliers = 0
        self.integrated = 0
        self.k_last = None
        self.still = np.zeros((NCOL, SEE_ROWS), np.int16)       # 같은 자리에 계속 있는 횟수(틱)
        self.still_prev = self.still

    def count(self, t):
        """시각 t 의 틱 번호와, 그 틱 구간 안에서의 위치(0~1)."""
        if self.phi is None:
            return self.k0, None
        x = (t - self.phi) / self.P
        k = int(np.floor(x))
        return k, x - k

    def ready(self):
        return self.phi is not None and (len(self.events) >= 3 or self.P_known)

    def feed(self, t, occ, vis=None):
        h = self.hist
        h.append((t, occ, vis))
        if len(h) == 4:
            (_, o0, _), (t1, o1, _), (t2, o2, _), (_, o3, _) = h
            if np.array_equal(o0, o1) and np.array_equal(o2, o3) and not np.array_equal(o1, o2):
                self._event(t1, t2)
        if len(h) >= 3:
            (_, oa, _), (tb, ob, vb), (_, oc, _) = list(h)[-3:]
            if np.array_equal(oa, ob) and np.array_equal(ob, oc):
                k, frac = self.count(tb)
                if frac is None or 0.1 <= frac <= 0.9:
                    self._integrate(k, ob, vb)

    def _event(self, lo, hi):
        mid = (lo + hi) / 2
        if self.phi is None:
            # 처음 몇 번은 차례대로 세면서, 줄이 내려가는 간격(게임마다 0.4초/0.5초 등)을 먼저 잼
            self.k0 += 1
            self.events.append((self.k0, lo, hi))
            if self.P_known:
                if hi - lo < 0.3:
                    self._fit()                      # 지난 판 간격으로 바로 시각을 맞춤
                return
            mids = [(e[1] + e[2]) / 2 for e in self.events if e[2] - e[1] < 0.3]
            ds = [b - a for a, b in zip(mids, mids[1:]) if 0.25 <= b - a <= 0.75]
            if len(ds) >= 3:
                self.P = float(np.median(ds))
                self._fit()
            return
        else:
            x = (mid - self.phi) / self.P
            k = int(round(x))
            if abs(x - k) > 0.3:
                if self.P_known and len(self.events) < 12:
                    self.misfit += 1
                    if self.misfit >= 2:
                        # 지난 판 간격이 이번 판과 다름 → 처음처럼 간격부터 다시 잼 (틱 번호는 이어서 셈)
                        print("  [알림] 띠가 내려오는 간격이 지난번과 달라서 다시 잼")
                        self.P_known = False
                        self.k0 = self.events[-1][0] + 1
                        self.phi = None
                        self.events = [(self.k0, lo, hi)]
                        self.cells[:] = -1
                        return
                self.outliers += 1
                if self.outliers >= 4:               # 시각이 계속 안 맞음 → 처음부터 다시 맞춤
                    self.events = [e for e in self.events[-1:]]
                    self.phi = mid - k * self.P
                    self.outliers = 0
                return
        self.outliers = 0
        self.events.append((k, lo, hi))
        self.events = self.events[-60:]
        self._fit()

    def _fit(self):
        ev = [e for e in self.events if e[2] - e[1] < 0.4] or self.events[-1:]
        ks = np.array([e[0] for e in ev], float)
        mids = np.array([(e[1] + e[2]) / 2 for e in ev])
        wts = 1.0 / np.maximum(np.array([e[2] - e[1] for e in ev]), 0.01) ** 2
        P = self.P
        if len(ev) >= 8 and ks.max() - ks.min() >= 8:
            km = (wts * ks).sum() / wts.sum()
            mm = (wts * mids).sum() / wts.sum()
            Pf = float((wts * (ks - km) * (mids - mm)).sum() / (wts * (ks - km) ** 2).sum())
            P = min(self.P * 1.03, max(self.P * 0.97, Pf))
        phi = float((wts * (mids - P * ks)).sum() / wts.sum())
        lo = max(e[1] - P * e[0] for e in ev[-12:])
        hi = min(e[2] - P * e[0] for e in ev[-12:])
        if lo <= hi:
            phi = (lo + hi) / 2
        self.phi, self.P = phi, P

    def _integrate(self, k, occ, vis=None):
        a0 = OFF - k
        if a0 < 0 or a0 + SEE_ROWS > self.cells.shape[1]:
            return
        # 띠는 틱마다 한 줄씩 내려가므로, 화면 같은 자리에 9틱 넘게 계속 보이는 색은 띠가 아님
        if k != self.k_last:
            consecutive = self.k_last is not None and k == self.k_last + 1
            self.still_prev = self.still if consecutive else np.zeros_like(self.still)
            self.k_last = k
        self.still = np.where(occ, self.still_prev + 1, 0)
        new = (occ & (self.still < 9)).astype(np.int8)
        if vis is not None:                  # 가려져서 안 보이는 칸은 전에 본 대로 둠
            new = np.where(vis, new, self.cells[:, a0:a0 + SEE_ROWS])
        self.cells[:, a0:a0 + SEE_ROWS] = new
        self.integrated += 1

    def present(self, i, k):
        """띠 자리 i 가 틱 k 구간에 박음질 중인지.

        D <= A : A~D 줄 사이 칸이 전부 띠  (A == D 면 그 한 줄)
        D >  A : A~D 줄 사이에 띠가 하나라도
        """
        lo, hi = min(self.A, self.D) - k + OFF, max(self.A, self.D) - k + OFF
        if lo < 0 or hi >= self.cells.shape[1]:
            return False
        seg = self.cells[i, lo:hi + 1] == 1
        return bool(seg.all() if self.D <= self.A else seg.any())

    def gains(self, k, horizon):
        """칸별·구간별 박을 수 있는 띠 수 (5 x horizon)."""
        occ = self.cells == 1
        js = np.arange(horizon)
        g = None
        for r in range(min(self.A, self.D), max(self.A, self.D) + 1):
            idx = np.clip(r - k + OFF - js, 0, self.cells.shape[1] - 1)
            m = occ[:, idx]
            g = m if g is None else (g & m if self.D <= self.A else g | m)
        g = g.astype(np.int16)
        return g[0::2] + g[1::2]


def plan_lanes(gain, cur, rem):
    """앞으로 박을 수 있는 띠가 가장 많아지는 칸 순서 → [지금 구간 칸, 다음 구간 칸, ...].

    rem: 지금 구간에서 남은 비율(0~1). 칸을 옮기면 그 구간 앞부분을 조금 잃는 것으로 계산.
    """
    H = gain.shape[1]
    V = np.array([gain[k, 0] * (rem if k == cur else max(0.0, rem - 0.35)) - 0.004 * abs(k - cur)
                  for k in range(5)], float)
    back = []
    for j in range(1, H):
        nv = np.empty(5)
        bp = np.empty(5, int)
        for k in range(5):
            best, arg = -1e9, k
            for p in range(5):
                cost = 0.0 if p == k else (0.01 + 0.02 * abs(p - k)
                                           + (0.3 * gain[k, j] if gain[p, j - 1] else 0.0))
                v = V[p] - cost
                if v > best:
                    best, arg = v, p
            nv[k] = best + gain[k, j]
            bp[k] = arg
        V = nv
        back.append(bp)
    k = int(np.argmax(V))
    path = [k]
    for bp in reversed(back):
        k = int(bp[k])
        path.append(k)
    path.reverse()
    return path


# ==================== 한 판 진행 ====================

def focus_game(w, force=False):
    """키보드 입력이 의장이 창으로 가게 함 (다른 창이 선택돼 있으면 제목줄을 한 번 누름)."""
    if not force:
        try:
            act = am._gw.getActiveWindow()
            if act is None or am._norm(act.title) == am._norm(am._layout["titles"]["card"]):
                return
        except Exception:
            return
    x = w.left + int(w.width * random.uniform(0.25, 0.6))
    y = w.top + max(6, int(w.height * 0.025))
    if not force:
        print("  의장이 창이 선택돼 있지 않아서 제목줄을 한 번 클릭")
    am.smooth_move_to(x, y, random.uniform(0.2, 0.32), bow=6)
    time.sleep(random.uniform(0.05, 0.1))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.05, 0.1))
    pyautogui.mouseUp()
    time.sleep(random.uniform(0.1, 0.2))


def covering_windows(w):
    """의장이 창 위에 떠서 겹친 창들의 제목 (화면 맨 위 창부터 의장이 창이 나오기 전까지)."""
    out = []
    try:
        hw = getattr(w, "_hWnd", None)
        for o in am._gw.getAllWindows():
            if (hw is not None and getattr(o, "_hWnd", None) == hw) or o is w:
                break
            t = str(o.title).strip()
            if not t or not window_shown(o):
                continue
            if o.left < w.left + w.width and w.left < o.left + o.width \
                    and o.top < w.top + w.height and w.top < o.top + o.height:
                out.append(t)
    except Exception:
        pass
    return out[:4]


_debug_saved = False


def wait_until(t):
    """t 시각까지 기다림 (마지막 2ms 는 바쁘게 기다려서 정확히 맞춤)."""
    while True:
        d = t - time.time()
        if d <= 0:
            return
        if d > 0.003:
            time.sleep(d - 0.002)


# 판이 바뀌어도 기억하는 값 (한 번 맞춘 박음질 줄 / 키 반응 시간은 다음 판에도 씀)
# 프로그램을 껐다 켜도 이어 쓰도록 sew_learn.json 에 저장함
LEARN_FILE = os.path.join(HERE, "sew_learn.json")
_learned = {"dA": 0, "dD": 0, "lat": [], "rb": None, "P": None, "geo": None}
_dumped = [0]
_win_seen = [None]          # 시작을 누른 뒤 의장이 창이 처음 보인 시각
_last_pt = [None]           # 지난 판에 마우스를 둔 자리 (다음 판 시작 누르자마자 그리로)


def load_learned():
    try:
        import json
        with open(LEARN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("lat") is not None:
            _learned["lat"] = [float(d["lat"])] * 3
        _learned["dA"] = int(d.get("dA2", 0))
        _learned["dD"] = int(d.get("dD2", 0))
        if d.get("rb"):
            _learned["rb"] = float(d["rb"])
        if d.get("P") and 0.25 <= float(d["P"]) <= 0.75:
            _learned["P"] = float(d["P"])
        if d.get("geo"):
            _learned["geo"] = d["geo"]
        print(f"지난번에 맞춘 값: 키 반응 {d.get('lat') or 0:.2f}초 · 시작 줄 {_learned['dA']:+d} · 끝 줄 {_learned['dD']:+d}"
              + (f" · 띠 간격 {_learned['P']:.3f}초" if _learned["P"] else ""))
    except Exception:
        pass


def save_learned():
    try:
        import json
        lat = float(np.median(_learned["lat"])) if _learned["lat"] else None
        with open(LEARN_FILE, "w", encoding="utf-8") as f:
            json.dump({"lat": lat, "dA2": _learned["dA"], "dD2": _learned["dD"], "rb": _learned["rb"],
                       "P": _learned["P"], "geo": _learned["geo"]}, f)
    except Exception:
        pass


class Sewing:
    """의장이 창 한 판 동안의 상태 (화면 읽기 / 칸 정하기 / 키).

    시간은 두 가지로 봄
      - 화면 시각: 화면에 띠가 내려가 보이는 때 (찍은 화면 기준)
      - 키 시각  : 키를 보내야 하는 때 = 화면 시각 - 반응 시간(self.comp)
        (키를 보내고 그게 화면 버튼 색으로 보일 때까지 걸린 시간을 직접 재서 그만큼 미리 보냄)
    """

    def __init__(self, sct, w):
        self.sct, self.w = sct, w
        self.res = {"score": 0.0, "secs": 0.0, "pen": 0, "presses": 0, "ok": False}
        self.keys = Keys()
        self.mover = Mover()
        self.pa = PRESS_AFTER
        self.rb = _learned["rb"] or RELEASE_BEFORE
        self.jit_pa = self.jit_rb = 0.0
        self.hold_off = 0.0
        self.scores = deque()                 # 최근 0.6초 점수 (빨간 실 확인)
        self.score_hist = deque()             # 최근 3초 점수 (뗀 뒤 확인)
        self.sc = None
        self.tf = self.tf_prev = 0.0
        self.btn = [None, None]
        self.lane = None
        self.target = 2
        self.last_k = None
        self.ev_start = self.ev_end = 0       # 누를 때 / 뗄 때 빨간 실 횟수 (보정용)
        self.iv = None                        # 한 버튼만 눌린 동안의 점수 기록 (화면 시각)
        self.stuck = 0
        self.ends = []                        # 띠 끝에서 뗀 뒤 점수 변화
        self.pending_end = None
        self.last_dbg = 0.0
        self.lat = list(_learned["lat"][-10:])  # 키 → 화면 반응 시간 기록
        self.pend = {}                        # 반응을 기다리는 키 동작 {키: (시각, 누름?)}
        self.log_i = 0
        self.noresp = 0
        self.got_resp = False                 # 이번 판에 키를 눌러서 버튼이 바뀌는 걸 한 번이라도 봤는지
        self.iter_dt = 0.02                   # 한 바퀴(화면 읽기+계산) 걸리는 시간
        self.dts = []
        self.dump = _dumped[0] < DUMP_GAMES
        self.dump_k = None
        self.dump_log = []
        self.dump_jpgs = []                   # (파일 이름, jpg) — 판이 끝나면 한꺼번에 저장 (게임 중엔 안 느려지게)
        self.t0 = time.time()
        seen = _win_seen[0]
        self.t_win = seen if seen is not None and 0 <= self.t0 - seen < 5 else self.t0   # 의장이 창이 뜬 시각
        _win_seen[0] = None
        self.t_ready = self.t_strip = self.t_press = None
        self.st_k = None
        self.st_tot = [0] * 5                 # 칸별: 바늘 줄에 띠가 있던 틱 수
        self.st_got = [0] * 5                 #       그중 박은 틱 수
        self.lane_miss = None                 # 바늘을 화면에서 못 찾기 시작한 시각
        self.lane_guess = 0                   # 바늘이 안 보여서 마우스 둔 칸으로 본 횟수
        self.cal_t = 0.0
        self.cal_obs = {}                     # 띠 자리별로 화면에서 본 띠 가운데 x
        self.cal_msg = False
        self.path = []

    @property
    def comp(self):
        if len(self.lat) < 2:
            return 0.0
        return float(min(0.45, max(0.0, np.median(self.lat[-12:]))))

    # ---------- 준비 ----------
    def setup(self):
        global _debug_saved
        w = self.w
        t0 = time.time()
        geo = img = None
        raised = False
        cache = _learned.get("geo") or {}
        while time.time() - t0 < 5 and running and alive:
            if not window_shown(w):
                return False
            img = shot(self.sct, w.left, w.top, w.width, w.height)
            geo = detect_geo(img)
            if geo is None and list(cache.get("size") or []) == [w.width, w.height]:
                g2 = Geo(tuple(cache["box"]), cache.get("line"))
                if g2.fabric_ok(img):
                    geo = g2                          # 지난 판과 같은 크기 창 → 그때 찾은 천 위치
            if geo is not None:
                break
            if not raised and time.time() - t0 > 0.6:
                raised = True                         # 다른 창에 가려졌을 수 있음 → 의장이 창을 맨 앞으로
                focus_game(w, force=True)
            time.sleep(0.05)
        if geo is None:
            if not (running and alive):
                return False
            geo = geo_from_layout(w)
            if geo is None:
                print("  [실패] 의장이 창에서 회색 천을 못 찾음 — sew_debug.png 를 보내주세요")
                if img is not None:
                    save_debug(img, Geo((0, 0, REF_W, 251)), os.path.join(HERE, "sew_debug.png"))
                return False
            print("  (천을 화면에서 못 찾아서 measure_sew.py 로 잰 모서리를 씀)")
        hit = geo.hit
        print(f"  천 {geo.R - geo.L:.0f}x{geo.B - geo.T:.0f} (배율 {geo.s:.2f}) · 박음질 줄 {hit}"
              + ("" if geo.line_found else " (빨간 실선 못 찾음 — 기본값)")
              + (f" · 키 반응 {self.comp:.2f}초 (지난 판에서 잰 값)" if len(self.lat) >= 2 else ""))
        vis = geo.lanes_visible(img)
        if not all(vis):
            hidden = ", ".join(f"{k + 1}번" for k, v in enumerate(vis) if not v)
            cover = covering_windows(w)
            print(f"  [주의] 천 {hidden} 칸이 가려져 보임" + (f" (위에 있는 창: {', '.join(cover)})" if cover else "")
                  + " → 의장이 창을 맨 앞으로")
            focus_game(w, force=True)
            img = shot(self.sct, w.left, w.top, w.width, w.height)
            vis = geo.lanes_visible(img)
            if not all(vis):
                print("  [주의] 그래도 가려짐 — 의장이 창을 가리는 창을 옆으로 옮겨 주세요 (그 칸은 띠가 안 보임)")
        if SAVE_DEBUG_SHOT and not _debug_saved and img is not None:
            save_debug(img, geo, os.path.join(HERE, "sew_debug.png"))
            _debug_saved = True
        if self.dump:
            self.dump_setup(img)
        _learned["geo"] = {"size": [w.width, w.height], "box": [float(v) for v in geo.box],
                           "line": float(geo.line) if geo.line_found else None}
        cx0, cy0, cx1, cy1 = geo.crop
        cx1, cy1 = min(cx1, w.width), min(cy1, w.height)
        self.g = geo.moved(cx0, cy0)
        self.ox, self.oy = cx0, cy0                 # 창 왼쪽 위 → 잘라 찍는 곳
        self.cw, self.ch = cx1 - cx0, cy1 - cy0
        self.trk = Tracker(hit, _learned["P"])
        self.hit0 = hit
        self.trk.A += _learned["dA"]
        self.trk.D += _learned["dD"]
        self.lane = self.g.needle_lane(self.grab())
        self.target = self.lane if self.lane is not None else 2
        focus_game(w)
        x, y = self.mouse_xy(self.target)
        am.smooth_move_to(x, y, random.uniform(0.1, 0.18), bow=4)
        _last_pt[0] = (int(x), int(y))
        return True

    def grab(self):
        return shot(self.sct, self.w.left + self.ox, self.w.top + self.oy, self.cw, self.ch)

    def mouse_xy(self, k):
        g = self.g
        return (self.w.left + self.ox + g.lane_x(k) + random.uniform(-0.12, 0.12) * REF_STEP * g.s,
                self.w.top + self.oy + g.mouse_y + random.uniform(-4, 4) * g.s)

    # ---------- 화면 한 장 ----------
    def frame(self):
        """화면을 읽어 띠/바늘/점수/버튼을 갱신. 천이 안 보이면 False."""
        ta = time.time()
        img = self.grab()
        tf = (ta + time.time()) / 2
        if not self.g.fabric_ok(img):
            return False
        occ, vis = self.g.occupancy(img)
        self.trk.feed(tf, occ, vis)
        nl = self.g.needle_lane(img)
        if nl is not None:
            self.lane = nl
            self.lane_miss = None
        elif self.lane_miss is None:
            self.lane_miss = tf
        elif (tf - self.lane_miss >= 0.25 and not self.mover.busy() and 0 <= self.target <= 4
              and self.lane != self.target):
            self.lane = self.target            # 바늘이 화면에서 안 보이면 마우스를 둔 칸에 있다고 봄
            self.lane_guess += 1
        if tf - self.cal_t >= 0.3:
            self.cal_t = tf
            self.calibrate(img)
        self.sc = self.g.read_score(img)
        self.tf_prev, self.tf = self.tf, tf
        btn = self.g.buttons(img)
        self.measure_latency(tf, btn)
        self.btn = btn
        if self.sc is not None:
            self.scores.append((tf, self.sc))
            while self.scores and tf - self.scores[0][0] > 0.6:
                self.scores.popleft()
            self.score_hist.append((tf, self.sc))
            while self.score_hist and tf - self.score_hist[0][0] > 3.0:
                self.score_hist.popleft()
            self.res["score"] = max(self.res["score"], self.sc)
        if self.dump:
            self.dump_frame(img, tf)
        return True

    def calibrate(self, img):
        """화면에 보이는 띠의 실제 가로 위치로 띠 자리를 맞춤 (창 크기/배율이 달라도 5번째 칸까지 정확히)."""
        g = self.g
        sub = img[g.ya:g.yb]
        if sub.size == 0:
            return
        b, gg, r = sub[..., 0], sub[..., 1], sub[..., 2]
        masks = ((r > 140) & (gg > b + 60) & (r >= gg - 10) & (b < 130),
                 (b > r + 60) & (b > gg + 20) & (b > 90))
        lim = 0.3 * REF_STEP * g.xs
        for c, m in enumerate(masks):
            col = m.sum(axis=0)
            on = col >= max(4, 0.8 * g.rh)
            n, x = len(on), 0
            while x < n:
                if not on[x]:
                    x += 1
                    continue
                x0 = x
                while x < n and on[x]:
                    x += 1
                if not 3 * g.s <= x - x0 <= 18 * g.s:
                    continue
                cxm = float((np.arange(x0, x) * col[x0:x]).sum() / col[x0:x].sum())
                d, k = min((abs(g.col_x(2 * k + c) - cxm), k) for k in range(5))
                if d <= lim:
                    self.cal_obs.setdefault(2 * k + c, deque(maxlen=8)).append(cxm)
        cols = {i: float(np.median(v)) for i, v in self.cal_obs.items() if len(v) >= 2}
        if len(cols) < 2:
            return
        ref = {i: (REF_YCOL0, REF_BCOL0)[i % 2] + REF_STEP * (i // 2) for i in range(NCOL)}
        xr = np.array([ref[i] for i in cols])
        if xr.max() - xr.min() < REF_STEP:
            return
        xs, xa = np.polyfit(xr, np.array([cols[i] for i in cols]), 1)
        if not 0.92 * g.s <= xs <= 1.08 * g.s:
            return
        moves = [(xa + ref[i] * xs) - g.col_x(i) for i in range(NCOL)]
        if max(abs(v) for v in moves) < 1.5:
            return
        g.set_x(float(xa), float(xs))
        if not self.cal_msg:
            self.cal_msg = True
            print(f"  [보정] 띠 자리를 화면에 보이는 띠에 맞춤 (5번째 칸 {moves[-1]:+.0f}px)")

    def lane_stats(self):
        """칸별로 '바늘 줄에 띠가 있던 틱' 과 '그때 실제로 박은 틱' 을 셈 (판 끝에 cmd 에 표시)."""
        k, Tv, _ = self.vis_times(self.tf)
        frac = (self.tf - Tv) / self.trk.P
        if k == self.st_k or not 0.35 <= frac <= 0.8:
            return
        self.st_k = k
        for i in range(NCOL):
            if self.trk.present(i, k):
                ln = i // 2
                self.st_tot[ln] += 1
                if self.t_strip is None:
                    self.t_strip = self.tf
                if self.lane == ln and self.btn[i % 2]:
                    self.st_got[ln] += 1

    # ---------- 분석용 기록 (DUMP_GAMES) ----------
    def dump_setup(self, img):
        try:
            import io
            from PIL import Image
            self.dump_jpgs.append(("창.png", Image.fromarray(img[:, :, ::-1].clip(0, 255).astype(np.uint8))))
            w = self.w
            mons = list(getattr(self.sct, "monitors", [])[1:])
            mon = next((m for m in mons if m["left"] <= w.left + w.width / 2 < m["left"] + m["width"]
                        and m["top"] <= w.top + w.height / 2 < m["top"] + m["height"]), None)
            if mon is not None:
                full = shot(self.sct, mon["left"], mon["top"], mon["width"], mon["height"])
                im = Image.fromarray(full[:, :, ::-1].clip(0, 255).astype(np.uint8))
                im = im.resize((im.width // 2, im.height // 2))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=80)
                self.dump_jpgs.append(("화면전체.jpg", buf.getvalue()))
        except Exception as e:
            print(f"  (분석용 첫 화면 저장 실패: {e})")

    def dump_frame(self, img, tf):
        """분석용: 화면을 읽을 때마다 한 줄 기록 + 틱마다 화면 한 장 (판이 끝나면 한꺼번에 저장)."""
        try:
            trk = self.trk
            k, frac = trk.count(tf)
            held = "".join("Y" if kk == LEFT_KEY else "B" for kk in self.keys.held()) or "-"
            btn = "".join("?" if v is None else ("1" if v else "0") for v in self.btn)
            fr = "" if frac is None else f"{frac:.2f}"
            self.dump_log.append(f"{tf - self.t0:7.3f} k={k} fr={fr} lane={self.lane} tgt={self.target}"
                                 f" mv={int(self.mover.busy())} keys={held} btn={btn} sc={self.sc}")
            if frac is None or not (0.4 < frac < 0.6) or k == self.dump_k or len(self.dump_jpgs) > 400:
                return
            self.dump_k = k
            import io
            from PIL import Image
            y1 = min(img.shape[0], int(self.g.line + 25 * self.g.s))
            buf = io.BytesIO()
            Image.fromarray(img[:y1, :, ::-1].clip(0, 255).astype(np.uint8)).save(buf, format="JPEG", quality=88)
            self.dump_jpgs.append((f"{tf - self.t0:07.3f}.jpg", buf.getvalue()))
            occ = self.g.occupancy(img)[0]
            mem = "|".join("".join("#" if trk.cells[i, r - k + OFF] == 1 else "." for r in range(12, 25))
                           for i in range(NCOL))
            self.dump_log.append(f"  TICK k={k} 화면줄0~17=" + "|".join("".join("#" if v else "." for v in occ[i])
                                                                    for i in range(NCOL))
                                 + f"  기억줄12~24={mem}  계획={self.path[:6]}  A={trk.A} D={trk.D} P={trk.P:.4f}")
        except Exception as e:
            print(f"  (분석용 기록 중지: {e})")
            self.dump = False

    def write_dump(self):
        try:
            _dumped[0] += 1
            d = os.path.join(HERE, "sew_frames", f"판{_dumped[0]}_{time.strftime('%H%M%S')}")
            os.makedirs(d, exist_ok=True)
            trk, g = self.trk, self.g
            lines = [f"phi={trk.phi - self.t0 if trk.phi else None} P={trk.P} A={trk.A} D={trk.D} "
                     f"box={g.box} clip={g.clip} rh={g.rh} line={g.line} comp={self.comp:.3f} "
                     f"xa={g.xa:.2f} xs={g.xs:.4f} 창뜬시각={self.t_win - self.t0:.3f}"]
            lines += [f"key {t - self.t0:.3f} {k} {'down' if on else 'up'}" for (t, k, on) in self.keys.log]
            lines += self.dump_log
            with open(os.path.join(d, "log.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            for name, data in self.dump_jpgs:
                if isinstance(data, bytes):
                    with open(os.path.join(d, name), "wb") as f:
                        f.write(data)
                else:
                    data.save(os.path.join(d, name))
            print(f"  (분석용 기록을 {d} 에 저장함 — 이 폴더를 압축해서 보내주세요)")
        except Exception as e:
            print(f"  (분석용 기록 저장 실패: {e})")

    def measure_latency(self, tf, btn):
        """키를 보낸 뒤 버튼 색이 바뀌어 보일 때까지 걸린 시간 = 키 → 화면 반응 시간."""
        log = self.keys.log
        while self.log_i < len(log):
            t, key, on = log[self.log_i]
            self.pend[key] = (t, on)
            self.log_i += 1
        for c, key in ((0, LEFT_KEY), (1, RIGHT_KEY)):
            p = self.pend.get(key)
            if p is None or btn[c] is None:
                continue
            t, on = p
            if tf <= t:
                continue
            if btn[c] == on and self.btn[c] is not None and self.btn[c] != on:
                lo = max(self.tf_prev, t)
                self.lat = (self.lat + [(lo + tf) / 2 - t])[-20:]
                del self.pend[key]
                self.got_resp = True
                self.noresp = 0
            elif btn[c] == on:
                del self.pend[key]                 # 이미 그 상태였음 → 못 잼
            elif tf - t > (1.0 if self.got_resp else 0.6):
                del self.pend[key]                 # 버튼이 안 바뀜 = 키가 게임에 안 감 (다른 창이 선택돼 있음)
                if on:
                    self.noresp += 1
                    # 판 시작 때 한 번도 반응이 없으면 바로 (띠를 놓치기 전에), 게임 중엔 3번 연속일 때
                    if self.noresp >= (3 if self.got_resp else 1):
                        self.noresp = 0
                        print("  [주의] 키를 눌러도 버튼이 안 바뀜 → 의장이 창을 선택하려고 제목줄 클릭")
                        self.keys.release_all()
                        focus_game(self.w, force=True)
                        self.target = -1              # 마우스를 다시 바늘 칸으로

    def times(self, now):
        """키 시각 기준 (틱 번호, 이번 구간 시작, 다음 구간 시작)."""
        c = self.comp
        k, _ = self.trk.count(now + c)
        T_cur = self.trk.phi + k * self.trk.P - c
        return k, T_cur, T_cur + self.trk.P

    def vis_times(self, t):
        """화면 시각 기준 (틱 번호, 이번 구간 시작, 다음 구간 시작)."""
        k, _ = self.trk.count(t)
        T_cur = self.trk.phi + k * self.trk.P
        return k, T_cur, T_cur + self.trk.P

    def score_at(self, t):
        best = None
        for (ts, s) in self.score_hist:
            if ts <= t:
                best = s
        return best

    # ---------- 구간이 바뀔 때 ----------
    def edge_evidence(self, i, kv):
        """점수가 깎인 구간 kv 가 띠의 첫 구간인지 마지막 구간인지 보고, 그쪽 끝만 한 칸 보정."""
        trk = self.trk
        if not trk.present(i, kv):
            return
        first = not trk.present(i, kv - 1)
        last = not trk.present(i, kv + 1)
        if first == last:
            return                                  # 한 칸짜리이거나 중간 → 어느 끝인지 모름
        if last:
            self.ev_end += 1
            if self.ev_end >= 2 and trk.D > self.hit0 - 2:
                trk.D -= 1
                self.ev_end = 0
                print("  [보정] 띠가 끝나는 걸 한 칸 일찍 보도록 맞춤 (뗄 때 빨간 실이 나와서)")
        else:
            self.ev_start += 1
            if self.ev_start >= 2 and trk.A < self.hit0 + 2:
                trk.A += 1
                self.ev_start = 0
                print("  [보정] 띠가 시작하는 걸 한 칸 늦게 보도록 맞춤 (누를 때 빨간 실이 나와서)")

    def new_interval(self, k):
        iv = self.iv
        if iv is not None and iv["n"] >= 3 and iv["t1"] - iv["t0"] >= 0.12:
            d = iv["s1"] - iv["s0"]
            obs = True if d > 0.6 else (False if d < -1.5 else None)
            if d == 0 and iv["t1"] - iv["t0"] >= 0.25:
                self.stuck += 1
                if self.stuck == 4:
                    print("  [주의] 버튼이 눌려도 점수가 안 움직임")
            elif d != 0:
                self.stuck = 0
        self.iv = None
        self.last_k = k
        self.jit_pa = random.uniform(-TIMING_JITTER, TIMING_JITTER)
        self.jit_rb = random.uniform(-TIMING_JITTER, TIMING_JITTER)

    def check_end(self, now):
        """띠 끝에서 뗀 뒤 점수가 조금씩 깎이면(늦게 뗌) 더 일찍 떼도록 맞춤."""
        pe = self.pending_end
        if pe is None or now < pe + self.comp + 0.45:
            return
        self.pending_end = None
        if self.sc is None or self.keys.held() or any(self.btn):
            return
        before = self.score_at(pe + self.comp - 0.05)
        if before is None:
            return
        self.ends = (self.ends + [self.sc - before])[-5:]
        if len(self.ends) >= 4 and np.mean(self.ends) < -0.6:
            self.rb = min(0.25, self.rb + 0.02)
            self.ends = []
            print(f"  [보정] 뗄 때 점수가 조금씩 깎임 → 띠 끝 {self.rb:.2f}초 전에 떼기")

    # ---------- 칸 정하기 ----------
    def plan(self, k, T_next, now):
        cur = self.lane if self.lane is not None else self.target
        gain = self.trk.gains(k, 22)
        path = plan_lanes(gain, cur, max(0.0, (T_next - now) / self.trk.P))
        self.path = path
        k0, k1 = path[0], path[1]
        if k0 != cur:
            tgt = k0
        elif k1 != cur and (gain[cur, 0] == 0 or now >= T_next - self.rb - 0.01):
            tgt = k1
        else:
            tgt = cur
        if tgt != self.target or (self.lane is not None and self.lane != self.target
                                  and not self.mover.busy()):
            self.keys.release_all()
            self.pending_end = None
            x, y = self.mouse_xy(tgt)
            lanes = abs(tgt - cur) if self.lane is not None else 2
            self.mover.go(x, y, now, max(1, lanes))
            self.target = tgt
        self.mover.step(now)
        return gain

    # ---------- 키 ----------
    def key_states(self, now):
        """지금 각 키를 누르고 있어야 하는지, 띠 끝이라 떼는 건지, 다음에 키를 바꿀 시각."""
        trk = self.trk
        k, T_cur, T_next = self.times(now)
        lane = self.lane
        ok = (lane is not None and lane == self.target and not self.mover.busy()
              and now >= self.hold_off)
        # 키 반응 시간을 아직 못 쟀으면(첫 띠) 조금 늦게 누르고 일찍 떼서 빨간 실이 안 나오게
        pa, rb = (self.pa, self.rb) if len(self.lat) >= 2 else (max(self.pa, 0.1), max(self.rb, 0.3))
        wants, ends, nxt = {}, {}, []
        for c, key in ((0, LEFT_KEY), (1, RIGHT_KEY)):
            want = end = False
            if ok:
                i = 2 * lane + c
                p0, p1, pm = trk.present(i, k), trk.present(i, k + 1), trk.present(i, k - 1)
                t_on = T_cur + pa + self.jit_pa
                t_off = T_next - rb - self.jit_rb
                if p0:
                    want = (p1 or now < t_off) and (pm or now >= t_on)
                    end = not p1 and now >= t_off
                    if want and not p1:
                        nxt.append(t_off)
                    if not want and not pm and now < t_on:
                        nxt.append(t_on)
                elif p1:
                    nxt.append(T_next + pa + self.jit_pa)
            wants[key], ends[key] = want, end
        nxt = [t for t in nxt if t > now]
        return wants, ends, (min(nxt) if nxt else None)

    def apply_keys(self, now):
        wants, ends, nxt = self.key_states(now)
        for key, want in wants.items():
            was = self.keys.down[key] is not None
            self.keys.set(key, want, now)
            if was and not want and ends[key]:
                self.pending_end = now
        self.keys.tick(now)
        return nxt

    def check_penalty(self, now):
        """누르고 있는데 점수가 깎이면(빨간 실) 바로 뗌."""
        if not self.keys.held() or self.sc is None or len(self.scores) < 2:
            return
        recent = max(s for (t, s) in self.scores if self.tf - t <= 0.3)
        if recent - self.sc < 2.5:
            return
        held = self.keys.held()
        since = now - min(t for t in self.keys.down.values() if t is not None)
        k, T_cur, T_next = self.times(now)
        self.keys.release_all()
        self.pending_end = None
        self.hold_off = T_next + 0.01
        self.res["pen"] += 1
        kv, Tv, _ = self.vis_times(self.tf - 0.04)
        print(f"  [빨간 실] 점수가 깎여서 바로 뗌 (깎이기 시작: 화면상 틱 뒤 {self.tf - 0.04 - Tv:.2f}초쯤"
              f" · 반응 {self.comp:.2f}초)")
        # 깎였다 = 그 구간에 띠가 없었다 → 박음질 줄 확인에 씀. 줄이 맞으면 타이밍을 조금 보정
        lit = [c for c in (0, 1) if self.btn[c]]
        cs = lit if len(lit) == 1 else ([0 if held[0] == LEFT_KEY else 1] if len(held) == 1 else [])
        if cs and self.lane is not None:
            self.edge_evidence(2 * self.lane + cs[0], kv)
        self.scores.clear()
        self.scores.append((self.tf, self.sc))

    def record_single(self):
        """버튼 하나만 눌려 보이는 동안의 점수 변화 기록 (화면 시각 — 박음질 줄 확인용)."""
        b = self.btn
        if b[0] is None or b[1] is None or self.sc is None or self.lane is None:
            return
        if b[0] and b[1]:
            self.iv = None
            return
        if not (b[0] or b[1]):
            return
        k, T_cur, T_next = self.vis_times(self.tf)
        if not (T_cur + 0.1 <= self.tf <= T_next - 0.08):
            return
        i = 2 * self.lane + (0 if b[0] else 1)
        iv = self.iv
        if iv is None or iv["i"] != i or iv["k"] != k:
            self.iv = {"i": i, "k": k, "t0": self.tf, "s0": self.sc, "t1": self.tf, "s1": self.sc, "n": 1}
        else:
            iv.update(t1=self.tf, s1=self.sc, n=iv["n"] + 1)

    # ---------- 한 판 ----------
    def run(self):
        t_start = time.time()
        if not self.setup():
            return self.res
        w = self.w
        lost = 0
        last_vk = None
        t_loop = time.time()
        try:
            while running and alive:
                if not window_shown(w):
                    break
                if time.time() - t_start > GAME_TIMEOUT:
                    print("  [주의] 한 판이 너무 오래 걸림 → 그만둠")
                    break
                if not self.frame():
                    self.keys.release_all()
                    lost += 1
                    if lost >= 8:
                        break
                    time.sleep(0.03)
                    continue
                lost = 0
                now = time.time()
                if not self.trk.ready():
                    self.mover.step(now)
                    time.sleep(LOOP_DT)
                    continue
                if self.t_ready is None:
                    self.t_ready = now
                self.lane_stats()
                kv = self.vis_times(self.tf)[0]
                if kv != last_vk:
                    last_vk = kv
                    self.new_interval(kv)
                self.record_single()
                k, T_cur, T_next = self.times(now)
                self.check_end(now)
                gain = self.plan(k, T_next, now)
                nxt = self.apply_keys(now)
                if self.t_press is None and self.keys.presses:
                    self.t_press = now
                self.check_penalty(now)
                if DEBUG and now - self.last_dbg > 0.5:
                    self.last_dbg = now
                    print(f"    틱{k} 칸{self.lane}->{self.target} 점수 {self.sc} 누름 {self.keys.held()} "
                          f"버튼 {self.btn} 반응 {self.comp:.2f}")
                # 한 바퀴 걸리는 시간 (화면 읽기가 느린 컴퓨터면 길어짐)
                t_now = time.time()
                dt = t_now - t_loop
                t_loop = t_now
                self.dts.append(dt)
                self.iter_dt = 0.8 * self.iter_dt + 0.2 * min(dt, 0.3)
                # 키를 바꿀 시각이 다음 화면 읽기보다 먼저 오면, 그때까지 기다렸다가 정확히 누르고/뗌
                if nxt is not None and nxt - time.time() < max(0.03, 1.5 * self.iter_dt + 0.01):
                    wait_until(nxt + 0.0005)
                    if window_shown(w):
                        self.mover.step(time.time())
                        self.apply_keys(time.time())
                else:
                    time.sleep(LOOP_DT)
        finally:
            self.keys.release_all()
        if self.dump and self.dump_log:
            self.write_dump()
        if len(self.lat) >= 2:
            _learned["lat"] = self.lat[-12:]
        if self.trk.phi is not None and len(self.trk.events) >= 20:
            _learned["P"] = float(self.trk.P)     # 다음 판은 첫 틱부터 바로 (간격을 다시 안 재도 됨)
        if self.res["score"] > 50:
            _learned["dA"] = self.trk.A - self.hit0
            _learned["dD"] = self.trk.D - self.hit0
            _learned["rb"] = self.rb
        save_learned()
        dts = np.array(self.dts[5:] or [0.0])
        print(f"  (키 반응 {self.comp:.2f}초 · 화면 한 바퀴 평균 {dts.mean() * 1000:.0f}ms"
              f" 최대 {dts.max() * 1000:.0f}ms · 시작 줄 {self.trk.A} · 끝 줄 {self.trk.D}"
              f" · 누름 지연 {self.pa:.2f} · 뗌 여유 {self.rb:.2f} · 띠 간격 {self.trk.P:.3f}초)")
        rel = lambda t: f"{t - self.t_win:.1f}초" if t is not None else "-"
        print(f"  (창 뜬 뒤: 준비 {rel(self.t_ready)} · 첫 띠가 바늘 줄에 {rel(self.t_strip)} · 첫 누름 {rel(self.t_press)})")
        print("  (칸별로 바늘 줄에 띠가 있던 틱 중 박은 틱: "
              + " · ".join(f"{k + 1}칸 {self.st_got[k]}/{self.st_tot[k]}" for k in range(5))
              + (f" · 바늘이 안 보여 마우스 칸으로 판단 {self.lane_guess}번" if self.lane_guess else "") + ")")
        self.res.update(secs=time.time() - t_start, presses=self.keys.presses,
                        ok=self.res["score"] >= 235)
        return self.res


def play_game(sct, w):
    """의장이 창이 떠 있는 동안 박음질. 끝나면 결과 dict."""
    return Sewing(sct, w).run()


# ==================== 제작 창 → 시작 ====================

def start_game(sct):
    """시작 버튼을 누르고 의장이 창이 뜨면 그 창을 반환."""
    stale = {getattr(x, "_hWnd", None) for x in am.find_windows("card")}
    am.human_click(am.START_BTN)
    print("  시작 버튼 클릭!")
    t0 = time.time()
    if _last_pt[0] is not None:
        # 창이 뜨는 동안 지난 판에 바늘을 두던 자리로 바로 옮겨 둠 (창은 매번 같은 자리에 뜸)
        x, y = _last_pt[0]
        am.smooth_move_to(x + random.randint(-8, 8), y + random.randint(-5, 5), random.uniform(0.12, 0.2), bow=5)
    while time.time() - t0 < 6:
        w = find_game_win(ignore=stale)
        if w is not None:
            _win_seen[0] = time.time()
            return w
        time.sleep(0.03)
    print("  [실패] 시작 후 6초 동안 '의장이' 창이 안 뜸")
    return None


def run_round(sct, tpl):
    """한 판: (이미 떠 있는 의장이 창이 있으면 그것부터) 재료 넣기 → 시작 → 박음질."""
    w = find_game_win()
    if w is None:
        if not am.open_furniture_window(sct):
            return None
        if not am.fill_slots(sct, tpl):
            return None
        w = start_game(sct)
        if w is None:
            return None
    else:
        print("  의장이 창이 이미 떠 있음 → 바로 박음질")
    res = play_game(sct, w)
    t0 = time.time()
    while find_game_win() is not None and time.time() - t0 < 3:
        time.sleep(0.2)
    return res


# ==================== 쉬기 ====================

_rest = {}


def _skewed(lo, hi):
    return random.triangular(lo, hi, lo + (hi - lo) * 0.3)


def _fmt(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}분 {s}초" if m else f"{s}초"


def find_red_close(sct, w):
    bw, bh = min(160, w.width), min(max(28, int(w.height * 0.09)), w.height)
    img = shot(sct, w.left + w.width - bw, w.top, bw, bh)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    ys, xs = np.nonzero((r > 190) & (g < 120) & (b < 120))
    if len(xs) < 20:
        return None
    return int(w.left + w.width - bw + xs.mean()), int(w.top + ys.mean())


def close_craft(sct):
    w = am.find_win("craft")
    if w is None:
        return
    pt = find_red_close(sct, w)
    if pt is not None:
        am.human_click(pt, jx=1, jy=1)
        time.sleep(random.uniform(0.6, 1.0))


def rest_for(sec, why, sct=None, away=False):
    if away and sct is not None:
        close_craft(sct)
        am._scan_cache = None
    end = time.time() + sec
    when = f" ({time.strftime('%H:%M', time.localtime(end))}에 다시 시작)" if sec >= 60 else ""
    print(f"[휴식] {why} — {_fmt(sec)}{when}")
    while running and alive and time.time() < end:
        time.sleep(0.3)


def maybe_rest(sct):
    if not REST:
        time.sleep(random.uniform(1.0, 2.0))
        return
    now = time.time()
    if "start" not in _rest:
        _rest.update(start=now, len=random.uniform(*SESSION_MINS) * 60, games=0,
                     short_at=random.randint(*SHORT_EVERY),
                     big_at=now + random.uniform(*BIG_EVERY_HOURS) * 3600)
    _rest["games"] += 1
    if now >= _rest["start"] + _rest["len"]:
        if now >= _rest["big_at"]:
            rest_for(_skewed(*BIG_MINS) * 60, "크게 쉬기", sct, away=True)
            _rest["big_at"] = time.time() + random.uniform(*BIG_EVERY_HOURS) * 3600
        else:
            rest_for(_skewed(*BREAK_MINS) * 60, "한참 했으니 자리 비움", sct, away=True)
        _rest.update(start=time.time(), len=random.uniform(*SESSION_MINS) * 60, games=0,
                     short_at=random.randint(*SHORT_EVERY))
        return
    if _rest["games"] >= _rest["short_at"]:
        rest_for(_skewed(*SHORT_SECS), f"잠깐 쉬기 ({_rest['games']}판 했음)")
        _rest["games"] = 0
        _rest["short_at"] = random.randint(*SHORT_EVERY)
        return
    time.sleep(_skewed(*BREATH_SECS))


# ==================== 실행 ====================

def check_layout():
    lay = am.load_layout()
    if lay is None:
        print("[중단] match_layout.json 이 없어요 — 먼저  py measure_sew.py")
        return False
    need = ("job_act", "slot1", "slot2", "cell_first", "cell_row1_last", "cell_row5_first", "start")
    miss = [n for n in need if n not in lay.get("points", {})]
    if miss:
        print(f"[중단] 측정값에 없는 것: {', '.join(miss)} — py measure_sew.py 로 다시 재기")
        return False
    if am._norm(lay.get("titles", {}).get("card", "")) != am._norm("의장이"):
        print("[중단] match_layout.json 이 의장이용이 아니에요 (주장이 것을 복사했나요?)"
              " — 이 폴더에서  py measure_sew.py")
        return False
    if am._gw is None:
        print("[중단] pygetwindow 가 없어요 — cmd 에서:  py -m pip install pygetwindow")
        return False
    return True


def worker():
    global running, alive
    try:
        if not check_layout():
            alive = False
            return
        am.RECIPE = list(RECIPE)
        am.NUM_SLOTS = NUM_SLOTS
        tpl = am.load_templates()
        names = {n for n, _ in RECIPE}
        tpl = {k: v for k, v in tpl.items() if k in names}
        missing = [n for n in names if n not in tpl]
        if missing:
            print(f"[중단] items 폴더에 그림이 없는 재료: {', '.join(missing)}")
            print("       제작 창을 띄우고  py auto_match.py 캡처  → 이름 바꾸기 → auto_sew.py 의 RECIPE 확인")
            alive = False
            return
        print("재료:", ", ".join(f"{n} x{c}" for n, c in RECIPE))
        load_learned()
        print("준비 완료 — F8 로 시작")
        games = wins = fails = 0
        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.15)
                    continue
                am.running = am.alive = True
                res = run_round(sct, tpl)
                if not running:
                    continue
                if res is None:
                    fails += 1
                    if fails >= FAIL_STOP:
                        running = False
                        fails = 0
                        print(f"⏸ {FAIL_STOP}번 연속 실패해서 멈춤 — 재료 확인 후 F8")
                        continue
                    print(f"[오류] 이번 판 실패 — {FAIL_WAIT}초 뒤 다시 (지금 바로: F8 두 번, 종료 F9)")
                    t0 = time.time()
                    while running and alive and time.time() - t0 < FAIL_WAIT:
                        time.sleep(0.2)
                    continue
                fails = 0
                games += 1
                wins += res["ok"]
                print(f"★ {games}판 끝 — {'성공' if res['ok'] else '실패?'} "
                      f"(점수 {res['score']:.0f} · {res['secs']:.0f}초 · 누름 {res['presses']}번"
                      f" · 빨간 실 {res['pen']}번) 누적 성공 {wins}/{games}")
                if MAX_GAMES and games >= MAX_GAMES:
                    running = False
                    print(f"⏸ {MAX_GAMES}판 다 했음")
                    continue
                maybe_rest(sct)
    except pyautogui.FailSafeException:
        print("\n[비상정지] 마우스가 화면 구석으로 갔습니다. 완전히 종료합니다.")
        alive = False
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        alive = False
    finally:
        for k in (LEFT_KEY, RIGHT_KEY):
            try:
                keyboard.release(k)
            except Exception:
                pass


def toggle():
    global running
    running = not running
    am.running = running
    am._scan_cache = None
    if running:
        _rest.clear()
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨 (지금 하던 동작이 끝나면 멈춤)")


def quit_all():
    global running, alive
    running = alive = False
    am.running = am.alive = False
    print("\n종료합니다...")


def hires_timer():
    """윈도우의 sleep 정밀도를 1ms 로 (박음질 타이밍이 중요해서)."""
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def main():
    hires_timer()
    print("=" * 56)
    print(" 의장이(재봉틀) 자동")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 56)
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
