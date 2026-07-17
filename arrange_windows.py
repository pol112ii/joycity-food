# -*- coding: utf-8 -*-
"""
게임 창 자동 정렬 도구.

매번 마우스로 창들을 제자리에 맞추는 대신, 이 스크립트가 창들을
저장해둔 위치로 한 번에 옮겨줌.

■ 처음 한 번 (위치 기억시키기):
  1. 조이톡2 / 아이템 / 음식만들기 / 직업 창을 모두 켜고
     마우스로 원하는 자리에 정확히 배치
  2. 실행:  py arrange_windows.py 저장
     → 지금 위치가 window_layout.json 파일에 저장됨

■ 그 다음부터 (매일 쓸 때):
  창들을 켜놓고 실행:  py arrange_windows.py
  → 모든 창이 저장된 자리로 자동 이동

※ 닫혀있는 창은 건너뜀 (예: 음식만들기 창을 안 켰으면 그냥 넘어감)
※ 컴퓨터마다 배치가 다르면 각 컴퓨터에서 '저장'을 한 번씩 하면 됨
   (window_layout.json은 컴퓨터마다 따로 생김)
"""

import os
import sys
import json

TITLES = ["조이톡2", "아이템", "음식만들기", "직업"]

LAYOUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "window_layout.json")


def find_window(gw, title):
    """제목이 정확히 title인 창을 찾음 (보이는 창 우선)."""
    cands = [w for w in gw.getAllWindows() if w.title == title and w.width > 0]
    if not cands:
        return None
    visible = [w for w in cands if getattr(w, "visible", True)]
    return (visible or cands)[0]


def save_layout(gw):
    layout = {}
    for title in TITLES:
        w = find_window(gw, title)
        if w is None:
            print(f"  [건너뜀] '{title}' 창을 못 찾음 (닫혀있으면 정상)")
            continue
        layout[title] = [w.left, w.top]
        print(f"  '{title}' 위치 저장: ({w.left}, {w.top})")
    if not layout:
        print("\n[실패] 저장할 창이 하나도 없습니다. 창들을 켜고 다시 실행하세요.")
        return
    with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! → {LAYOUT_FILE}")
    print("이제부터는 그냥 실행만 하면 창들이 이 자리로 이동합니다.")


def apply_layout(gw):
    if not os.path.exists(LAYOUT_FILE):
        print("[안내] 저장된 위치가 없습니다. 먼저 창들을 원하는 자리에 배치한 뒤")
        print("       py arrange_windows.py 저장")
        print("       을 실행해서 위치를 기억시켜 주세요.")
        return
    with open(LAYOUT_FILE, encoding="utf-8") as f:
        layout = json.load(f)
    moved = 0
    for title, (x, y) in layout.items():
        w = find_window(gw, title)
        if w is None:
            print(f"  [건너뜀] '{title}' 창이 안 열려있음")
            continue
        if (w.left, w.top) == (x, y):
            print(f"  '{title}' 이미 제자리 ({x}, {y})")
            continue
        w.moveTo(x, y)
        print(f"  '{title}' 이동: ({w.left}, {w.top}) → ({x}, {y})")
        moved += 1
    print(f"\n완료! {moved}개 창을 옮겼습니다.")


def main():
    try:
        import pygetwindow as gw
    except ImportError:
        print("[에러] pygetwindow가 설치되어 있지 않습니다.")
        print("       cmd에서:  py -m pip install pygetwindow")
        return

    if len(sys.argv) > 1 and sys.argv[1] in ("저장", "save"):
        print("현재 창 위치를 저장합니다...\n")
        save_layout(gw)
    else:
        print("저장된 위치로 창들을 이동합니다...\n")
        apply_layout(gw)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
