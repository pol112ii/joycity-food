# -*- coding: utf-8 -*-
"""
가구만들기(그림 맞추기) 인식 확인 도구.  ※ 클릭은 절대 안 함 — 보기만 함

auto_match.py 를 돌리기 전에, 봇이 카드판을 제대로 '보고 있는지'
먼저 눈으로 확인하는 용도. scan_test.py 와 같은 역할.

■ 사용법
  1. 가구만들기 창을 열고 게임을 시작해서 카드판이 보이게 함
  2. cmd 에서:  py match_test.py
  3. 1초마다 5x5 판을 읽어서 화면에 표시함. 끝내려면 Ctrl+C

■ 화면에 나오는 기호
  ?  = 뒷면 (초록 원)          안 열린 카드
  O  = 열림 (파란 원)          그림이 보이는 카드
  X  = 폭탄 (주황 원)
  .  = 판정 실패               ← 이게 나오면 좌표나 기준값이 틀린 것

■ 확인할 것
  - 게임 화면과 표시되는 판이 똑같은가
  - 카드를 뒤집으면 그 자리가 ? → O 로 바뀌는가
  - 폭탄이 나오면 X 로 잡히는가
  - 열린 카드가 2장 이상일 때, 같은 그림끼리 '짝 후보'로 묶이는가

문제가 있으면 debug_cards.png 파일이 저장되니 그걸 보고 좌표를 조정하면 됨.
"""

import os
import time

import numpy as np
import mss

# ===================== 이 컴퓨터 좌표 (measure.py 로 잰 값) =====================
CARD1_CENTER = (1651, 167)   # 카드판 1행1열 중심
CARD_PITCH_X = 45.0          # 옆 칸까지 가로 간격  ((1831-1651)/4)
CARD_PITCH_Y = 45.25         # 아래 칸까지 세로 간격 ((348-167)/4)
GRID = 5                     # 5x5

# 가구만들기 창이 열려있는지 확인할 기준점 (창 안 고정 초록 배경)
WIN_POINT = (1588, 293)
WIN_RGB = (23, 59, 21)
WIN_TOL = 40                 # 색 차이 허용치

# ===================== 인식 기준 (보통 안 건드려도 됨) =====================
RING_IN, RING_OUT = 12, 16   # 카드 '배경 원' 색을 볼 고리 반지름
                             # (원 반지름이 약 17px, 안쪽 그림은 반지름 11 이내)
IMG_R = 13                   # 그림 비교에 쓸 정사각형 반쪽 크기 (26x26)
SURE = 0.50                  # 이 비율 이상이어야 그 색으로 확신.
                             # 실측: 맞는 색은 0.68~0.87, 틀린 색은 0.02 이하라
                             # 0.5면 여유가 충분함 (0.75로 하면 붉은 가구가 걸림)
SAME_DIFF = 34               # 두 카드 그림 차이가 이 값 이하면 '같은 그림'으로 봄

DEBUG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "debug_cards.png")

_yy, _xx = np.mgrid[-RING_OUT:RING_OUT + 1, -RING_OUT:RING_OUT + 1]
_dist = np.sqrt(_yy ** 2 + _xx ** 2)
RING = (_dist >= RING_IN) & (_dist <= RING_OUT)


def card_center(r, c):
    """r행 c열(0부터) 카드의 화면 중심 좌표."""
    return (int(round(CARD1_CENTER[0] + c * CARD_PITCH_X)),
            int(round(CARD1_CENTER[1] + r * CARD_PITCH_Y)))


def grab(sct, cx, cy, half):
    shot = sct.grab({"left": cx - half, "top": cy - half,
                     "width": half * 2 + 1, "height": half * 2 + 1})
    return np.asarray(shot, dtype=int)[:, :, :3][:, :, ::-1]   # BGRA → RGB


def card_state(sct, r, c):
    """카드 상태를 '?'(뒷면) / 'O'(열림) / 'X'(폭탄) / '.'(판정실패) 로 반환."""
    cx, cy = card_center(r, c)
    px = grab(sct, cx, cy, RING_OUT)[RING]
    R, G, B = px[:, 0], px[:, 1], px[:, 2]
    green = ((G > 110) & (G > R + 35) & (G > B + 35)).mean()
    blue = ((B > 115) & (B > R + 30) & (B > G + 5)).mean()
    orange = ((R > 170) & (G > 60) & (G < 150) & (B < 85) & (R > B + 110)).mean()
    best = max(green, blue, orange)
    if best < SURE:
        return "."
    return "?" if best == green else ("O" if best == blue else "X")


def card_image(sct, r, c):
    """그림 비교용으로 카드 가운데를 잘라옴."""
    cx, cy = card_center(r, c)
    return grab(sct, cx, cy, IMG_R)


def window_open(sct):
    """가구만들기 창이 열려있는지 (기준점 색이 맞는지)."""
    px = grab(sct, WIN_POINT[0], WIN_POINT[1], 2).reshape(-1, 3)
    return bool(np.abs(px - np.array(WIN_RGB)).sum(axis=1).min() <= WIN_TOL)


def read_board(sct):
    states = [[card_state(sct, r, c) for c in range(GRID)] for r in range(GRID)]
    images = {(r, c): card_image(sct, r, c)
              for r in range(GRID) for c in range(GRID) if states[r][c] == "O"}
    return states, images


def find_pairs(images):
    """열린 카드들끼리 비교해서 같은 그림으로 보이는 짝을 찾음."""
    ks = list(images)
    scored = []
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            scored.append((float(np.abs(images[a] - images[b]).mean()), a, b))
    scored.sort()
    used, pairs = set(), []
    for d, a, b in scored:
        if d > SAME_DIFF:
            break
        if a in used or b in used:
            continue
        used.update((a, b))
        pairs.append((d, a, b))
    return pairs, scored


def save_debug(sct):
    """카드판 전체를 캡처하고 격자를 그려서 저장 — 좌표가 맞는지 눈으로 확인용."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (pillow 가 없어서 debug 이미지는 건너뜀)")
        return
    x0, y0 = card_center(0, 0)
    x1, y1 = card_center(GRID - 1, GRID - 1)
    m = 30
    left, top = x0 - m, y0 - m
    w, h = (x1 - x0) + m * 2, (y1 - y0) + m * 2
    shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    for r in range(GRID):
        for c in range(GRID):
            cx, cy = card_center(r, c)
            px, py = (cx - left) * 2, (cy - top) * 2
            d.ellipse((px - RING_OUT * 2, py - RING_OUT * 2,
                       px + RING_OUT * 2, py + RING_OUT * 2),
                      outline=(255, 0, 0), width=2)
            d.text((px - 8, py - 6), f"{r+1}{c+1}", fill=(255, 255, 0))
    img.save(DEBUG_FILE)
    print(f"  격자 확인용 이미지 저장: {DEBUG_FILE}")
    print("  → 빨간 동그라미가 카드에 정확히 겹쳐야 좌표가 맞는 것")


def main():
    print("=" * 52)
    print(" 가구만들기 인식 확인 (클릭 안 함, 보기만)")
    print(" 끝내려면 Ctrl+C")
    print("=" * 52)
    with mss.mss() as sct:
        save_debug(sct)
        print()
        while True:
            opened = window_open(sct)
            states, images = read_board(sct)
            os.system("")     # 윈도우 콘솔 출력 정리용 (아무 동작 안 함)
            print("\n" + "-" * 52)
            print(f"가구만들기 창: {'열림' if opened else '안 보임 ← 좌표/색 확인 필요'}")
            for r in range(GRID):
                print("   " + "  ".join(states[r][c] for c in range(GRID)))
            n_back = sum(row.count("?") for row in states)
            n_open = sum(row.count("O") for row in states)
            n_bomb = sum(row.count("X") for row in states)
            n_bad = sum(row.count(".") for row in states)
            print(f"   뒷면 {n_back} · 열림 {n_open} · 폭탄 {n_bomb}"
                  + (f" · 판정실패 {n_bad} ←확인필요" if n_bad else ""))
            if n_bomb:
                pos = [f"({r+1},{c+1})" for r in range(GRID) for c in range(GRID)
                       if states[r][c] == "X"]
                print(f"   💣 폭탄: {' '.join(pos)}")
            if len(images) >= 2:
                pairs, scored = find_pairs(images)
                if pairs:
                    print("   같은 그림으로 보이는 짝:")
                    for d, a, b in pairs:
                        print(f"     ({a[0]+1},{a[1]+1}) ↔ ({b[0]+1},{b[1]+1})"
                              f"   차이 {d:.1f}")
                if scored:
                    print(f"   (가장 비슷한 차이 {scored[0][0]:.1f}"
                          f" / 가장 다른 차이 {scored[-1][0]:.1f}"
                          f" / 같다고 보는 기준 {SAME_DIFF} 이하)")
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n종료됨.")
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        input("\n엔터를 누르면 창이 닫힙니다...")
