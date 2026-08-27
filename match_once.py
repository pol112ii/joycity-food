# -*- coding: utf-8 -*-
"""
가구만들기 한 판만 돌려보는 시험용 프로그램.

auto_match.py(전체 자동)를 돌리기 전에, 짝맞추기 부분만 따로 확인하는 용도.
재료 넣기 / 창 열기는 하지 않고, 이미 준비된 상태에서 시작 버튼부터 누름.

■ 사용법
  1. 가구만들기 창을 열고, 재료를 직접 넣어서 '시작' 버튼을 누를 수 있는 상태로 만듦
  2. cmd 에서:  py match_once.py
  3. F8 을 누르면 → 시작 버튼 클릭 → 카드 짝맞추기 → 한 판 끝나면 자동 종료

  F9 = 즉시 종료.  비상시: 마우스를 화면 왼쪽 위 구석으로!

■ 좌표는 auto_match.py 것을 그대로 씀
  좌표를 고쳐야 하면 auto_match.py 위쪽만 고치면 여기도 같이 적용됨.
"""

import os
import sys
import time
import threading

# 임포트를 감싸서, 실패했을 때 창이 그냥 닫히지 않고 원인을 보여주게 함
try:
    import mss
    import keyboard
    import pyautogui
except ImportError as e:
    print("[에러] 필요한 프로그램이 설치되어 있지 않습니다:", e)
    print()
    print("cmd 에서 아래를 실행하세요:")
    print("  py -m pip install mss numpy pyautogui keyboard pillow pygetwindow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

try:
    import auto_match as am
except ImportError as e:
    here = os.path.dirname(os.path.abspath(__file__))
    print("[에러] auto_match.py 를 찾을 수 없습니다:", e)
    print()
    print(f"match_once.py 는 auto_match.py 와 같은 폴더에 있어야 합니다.")
    print(f"지금 폴더: {here}")
    print(f"이 폴더의 py 파일: "
          f"{', '.join(f for f in os.listdir(here) if f.endswith('.py')) or '(없음)'}")
    print()
    print("cmd 에서 아래를 실행해서 받으세요:")
    print('  curl -o auto_match.py '
          'https://raw.githubusercontent.com/pol112ii/joycity-food/main/auto_match.py')
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)
except Exception:
    import traceback
    print("[에러] auto_match.py 를 불러오다가 문제가 생겼습니다:\n")
    traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)


def main():
    print("=" * 52)
    print(" 가구만들기 한 판 시험 (짝맞추기만)")
    print(" 재료를 넣고 '시작' 을 누를 수 있는 상태로 만든 뒤 F8")
    print(" F8 = 시작    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print("=" * 52)

    state = {"go": False, "alive": True}

    def go():
        if not state["go"]:
            state["go"] = True
            print("\n▶ 시작합니다...")

    def stop():
        state["alive"] = False
        am.alive = False
        am.running = False
        print("\n종료합니다...")

    keyboard.add_hotkey("f8", go)
    keyboard.add_hotkey("f9", stop)

    def work():
        try:
            with mss.mss() as sct:
                while state["alive"] and not state["go"]:
                    time.sleep(0.15)
                if not state["alive"]:
                    return

                if not am.window_open(sct):
                    print("[중단] 가구만들기 창이 안 보입니다.")
                    print("       창을 열고 다시 실행하거나, auto_match.py 의")
                    print(f"       WIN_POINT{am.WIN_POINT} / WIN_RGB{am.WIN_RGB} 를 확인하세요.")
                    state["alive"] = False
                    return
                print("가구만들기 창 열림 확인")

                # play_board 안에서 running/alive 를 보므로 켜줌
                am.running = True
                am.alive = True

                if not am.press_start(sct):
                    print("[중단] 시작 버튼을 눌렀는데 카드판이 안 보입니다.")
                    print("       재료가 다 들어갔는지, START_BTN 좌표가 맞는지 확인하세요.")
                    state["alive"] = False
                    return

                t0 = time.time()
                ok, stats = am.play_board(sct)
                elapsed = time.time() - t0

                print("\n" + "=" * 52)
                if ok:
                    print(" 한 판 완료!")
                else:
                    print(" 한 판을 끝내지 못했습니다.")
                print(f"   걸린 시간 : {elapsed:.1f}초")
                print(f"   카드 클릭 : {stats['clicks']}회")
                print(f"   폭탄 밟음 : {stats['bombs']}회")
                print("=" * 52)
                if ok:
                    print(" 잘 됐으면 auto_match.py 로 전체 자동을 돌리면 됩니다.")
                    print(" (auto_match.py 위쪽 RECIPE 에 이번 재료를 적어야 함)")
                state["alive"] = False
        except pyautogui.FailSafeException:
            print("\n[비상정지] 마우스가 화면 구석으로 갔습니다.")
            state["alive"] = False
        except Exception:
            import traceback
            print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
            traceback.print_exc()
            state["alive"] = False

    t = threading.Thread(target=work, daemon=True)
    t.start()
    while state["alive"]:
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
