# -*- coding: utf-8 -*-
"""
'매크로 방지 확인' 창 감시 — 뜨면 봇을 바로 멈추고 텔레그램으로 계속 알림.

  - 1초마다 조이톡 창을 봐서 확인 창(남색 상자 + 파란 [확인] 버튼 + 빨간 '남은 시간')을 찾음
  - 찾으면: 봇 정지 · 키 떼기 → 텔레그램에 확인 창 사진 + 1초마다 알림 메시지
  - 텔레그램에 숫자 4자리를 답장하면 봇이 입력칸에 치고 [확인]을 누름
    (숫자를 읽는 건 사람 — 봇은 받은 숫자를 대신 쳐주기만 함. 다른 답장은 알림만 멈춤)
    여러 대가 동시에 뜨면: 그 컴퓨터 알림(사진/메시지)에 '답장'으로 숫자를 보내면 그 컴퓨터만 입력
    (또는 '3042 규남' 처럼 이름 일부를 붙이기)
  - 확인 창이 사라지면(입력 완료) 잠깐 쉬었다가 하던 걸 이어서 함
  - 40초가 지나도 안 사라지면 정지한 채로 둠 (접속이 끊겼을 수 있음)

봇이 화면의 숫자를 읽지는 않음 (사람이 보낸 숫자만 입력).
시험:  py auto_cook.py 매크로검사   (지금 화면에 확인 창이 있는지만 검사하고 그림 저장)
"""

import os
import time
import json
import threading

import numpy as np

# ----- 텔레그램 (주장이 폴더에서만 채움 — 식장이는 auto_cook.py 의 설정을 그대로 씀) -----
TELEGRAM_TOKEN = ""      # ← 봇 토큰 (저장소가 공개라서 깃허브엔 안 올림)
TELEGRAM_CHAT_ID = ""    # ← chat_id
NOTIFY_NAME = ""         # ← 알림 앞에 붙는 이름 (예: "정희꾸린노트북")

CHECK_SEC = 0.5          # 감시 간격(초) — 뜨면 0.2초 뒤 한 번 더 보고 바로 알림
ALERT_EVERY = 1.0        # 텔레그램 알림 간격(초) — 텔레그램은 1초에 1번보다 자주 보내면 막힘
ALERT_SECS = 32          # 알림을 계속 보내는 최대 시간(초) — 확인 창 제한시간 30초
GIVE_UP_SECS = 45        # 이만큼 지나도 확인 창이 안 사라지면 정지한 채로 둠
RESUME_WAIT = (3, 6)     # 확인 창이 사라진 뒤 다시 시작하기까지 쉬는 시간(초)
MAIN_TITLE = "조이톡"     # 게임 본 창 제목 (이 창 안에서 찾음. 못 찾으면 주 모니터 전체)

HERE = os.path.dirname(os.path.abspath(__file__))


# ==================== 화면에서 확인 창 찾기 ====================

def _largest_box(mask, cell=4):
    """mask 를 cell 단위로 줄여서 가장 큰 덩어리의 (x0, y0, x1, y1, 채움비율)."""
    h, w = mask.shape
    H, W = h // cell, w // cell
    if H < 4 or W < 4:
        return None
    m = mask[:H * cell, :W * cell].reshape(H, cell, W, cell).mean(axis=(1, 3)) > 0.5
    seen = np.zeros_like(m)
    best = None
    for y in range(H):
        for x in range(W):
            if not m[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            n = 0
            y0 = y1 = y
            x0 = x1 = x
            while stack:
                cy, cx = stack.pop()
                n += 1
                y0, y1, x0, x1 = min(y0, cy), max(y1, cy), min(x0, cx), max(x1, cx)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if best is None or n > best[0]:
                best = (n, x0, y0, x1, y1)
    if best is None:
        return None
    n, x0, y0, x1, y1 = best
    fill = n / float((x1 - x0 + 1) * (y1 - y0 + 1))
    return x0 * cell, y0 * cell, (x1 + 1) * cell, (y1 + 1) * cell, fill


def detect(img):
    """img: 조이톡 창 그림(RGB). 확인 창이 있으면 그 상자 (x0, y0, x1, y1), 없으면 None."""
    a = img.astype(np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    h, w = R.shape
    navy = (B >= 28) & (B <= 95) & (B - R >= 8) & (B - G >= 5) & (R <= 60) & (G <= 75)
    if navy.mean() < 0.03:
        return None
    box = _largest_box(navy, cell=max(4, w // 160))
    if box is None:
        return None
    x0, y0, x1, y1, fill = box
    bw, bh = x1 - x0, y1 - y0
    if not (0.15 * w <= bw <= 0.65 * w and 0.25 * h <= bh <= 0.85 * h):
        return None
    if fill < 0.5 or not (0.6 <= bh / max(bw, 1) <= 1.6):
        return None
    if abs((x0 + x1) / 2 - w / 2) > 0.25 * w:
        return None
    # 빨간 '남은 시간' 글자 (상자 가운데 높이)
    mid = a[y0 + int(bh * 0.4):y0 + int(bh * 0.75), x0:x1]
    r, g, b = mid[..., 0], mid[..., 1], mid[..., 2]
    red = ((r > 140) & (g < 115) & (b < 115) & (r - g > 60)).sum()
    # 아래쪽 파란 [확인] 버튼 (가로로 길게 파란 줄)
    low = a[y0 + int(bh * 0.7):y1, x0:x1]
    r, g, b = low[..., 0], low[..., 1], low[..., 2]
    blue_rows = ((b - r > 20) & (b > 50)).mean(axis=1) > 0.55
    run = best = 0
    for v in blue_rows:
        run = run + 1 if v else 0
        best = max(best, run)
    scale = max(1.0, bw / 300.0)
    if red >= 12 * scale or best >= max(3, int(bh * 0.04)):
        return (x0, y0, x1, y1)
    return None


def main_rect(bot):
    """조이톡 본 창의 (left, top, width, height). 못 찾으면 주 모니터."""
    try:
        if bot._gw is not None:
            want = "".join(MAIN_TITLE.split())
            for w in bot._gw.getAllWindows():
                if "".join(str(w.title).split()).startswith(want) and w.width > 300 and w.height > 300 \
                        and not getattr(w, "isMinimized", False) and w.left > -10000:
                    return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


def grab(sct, rect):
    if rect is None:
        mon = sct.monitors[1]
        rect = (mon["left"], mon["top"], mon["width"], mon["height"])
    l, t, w, h = rect
    s = sct.grab({"left": int(l), "top": int(t), "width": int(w), "height": int(h)})
    return np.asarray(s)[:, :, :3][:, :, ::-1].copy()      # RGB


def save_png(img, name):
    try:
        from PIL import Image
        Image.fromarray(img.astype(np.uint8)).save(os.path.join(HERE, name))
    except Exception:
        pass


def jpeg_bytes(img, enlarge=1):
    import io
    from PIL import Image
    im = Image.fromarray(img.astype(np.uint8))
    if enlarge != 1:
        im = im.resize((im.width * enlarge, im.height * enlarge))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ==================== 텔레그램 ====================

def _tg_ok(bot):
    return bool(getattr(bot, "TELEGRAM_TOKEN", "") and getattr(bot, "TELEGRAM_CHAT_ID", ""))


def _latest_update(bot):
    """가장 최근 텔레그램 메시지의 (update_id, chat_id, 글자). 실패하면 None."""
    try:
        url = f"https://api.telegram.org/bot{bot.TELEGRAM_TOKEN}/getUpdates?offset=-1&timeout=0"
        resp = bot._tg_urlopen(url, timeout=5)
        res = json.loads(resp.read().decode()).get("result", [])
        if not res:
            return (0, "", "")
        u = res[-1]
        msg = u.get("message") or {}
        return (u.get("update_id", 0), str((msg.get("chat") or {}).get("id", "")),
                (msg.get("text") or "").strip())
    except Exception:
        return None


def _new_updates(bot, after):
    """after 보다 새 텔레그램 메시지 → (마지막 update_id, [(글자, 답장한 원래 메시지 글자), ...]).
    최근 10개까지 봄 — 여러 컴퓨터에 연달아 답장해도 안 놓치게."""
    try:
        url = f"https://api.telegram.org/bot{bot.TELEGRAM_TOKEN}/getUpdates?offset=-10&timeout=0"
        resp = bot._tg_urlopen(url, timeout=5)
        res = json.loads(resp.read().decode()).get("result", [])
    except Exception:
        return after, []
    out = []
    for u in res:
        uid = u.get("update_id", 0)
        if uid <= after:
            continue
        after = uid
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id", "")) != str(bot.TELEGRAM_CHAT_ID):
            continue
        rep = msg.get("reply_to_message") or {}
        out.append(((msg.get("text") or "").strip(), rep.get("text") or rep.get("caption") or ""))
    return after, out


_hold_until = [0.0]                    # 텔레그램이 '너무 자주'라고 하면 이때까지 반복 알림 쉼
_fails = [0]                           # 이번 확인 창에서 텔레그램 보내기 실패 횟수


def log(msg):
    """macro_log.txt 에 시각과 함께 기록 (알림이 안 왔을 때 원인 찾기용)."""
    try:
        with open(os.path.join(HERE, "macro_log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%m-%d %H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d} {msg}\n")
    except Exception:
        pass


def _send(bot, text, retry=False):
    for attempt in range(2 if retry else 1):
        try:
            bot._send_telegram(text)
            log("텔레그램 보냄: " + text[:40])
            return True
        except Exception as e:
            _fails[0] += 1
            log(f"텔레그램 실패: {e}")
            if _fails[0] in (1, 5, 20):
                print(f"  [텔레그램 보내기 실패] {e}  (인터넷/토큰 확인 — macro_log.txt 에 기록)")
            if "429" in str(e):
                _hold_until[0] = time.time() + 3   # 여러 대가 동시에 보내면 자주 막힘 → 반복 알림만 잠깐 쉼
            if attempt == 0 and retry:
                time.sleep(1.5)
    return False


_busy = [False]


def _send_bg(bot, text):
    """기다리지 않고 보냄 (인터넷이 느려도 감시/답장 확인이 멈추지 않게). 앞의 것이 아직 가는 중이면 건너뜀."""
    if _busy[0]:
        return
    _busy[0] = True

    def go():
        try:
            _send(bot, text)
        finally:
            _busy[0] = False
    threading.Thread(target=go, daemon=True).start()


def for_me(text, reply, name):
    """이 메시지가 이 컴퓨터한테 온 건지.
    알림에 '답장'으로 보냈으면 그 알림을 보낸 컴퓨터만, '3042 규남' 처럼 이름 일부를 붙였으면
    그 이름의 컴퓨터만, 그냥 숫자만 보냈으면 확인 창이 떠 있는 모든 컴퓨터."""
    if "[" in reply:
        return f"[{name}]" in reply
    rest = "".join(ch for ch in text if not ch.isdigit() and not ch.isspace())
    if parse_code(text) and rest and rest not in name:
        return False
    return True


def parse_code(text):
    """메시지에서 숫자 4자리 → '1234'. 4자리가 아니면 None."""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == 4 else None


# ==================== 확인 창이 떴을 때 ====================

def parts(img, box):
    """확인 창 안의 (입력칸 가운데, [확인] 버튼 가운데) — 창 그림 좌표."""
    x0, y0, x1, y1 = box
    bh = y1 - y0
    a = img[y0:y1, x0:x1].astype(np.int16)
    blue = ((a[..., 2] - a[..., 0] > 20) & (a[..., 2] > 50)).mean(axis=1) > 0.55
    rows = [y for y in range(int(bh * 0.7), bh) if blue[y]]
    by = (rows[0] + rows[-1]) / 2 if rows else bh * 0.90
    iy = bh * 0.695 if not rows else min(bh * 0.695, rows[0] - bh * 0.15)
    cx = (x0 + x1) / 2
    return (cx, y0 + iy), (cx, y0 + by)


def enter_code(bot, rect, box, img, code):
    """사람이 보낸 숫자를 입력칸에 치고 [확인]을 누름."""
    l, t = (rect[0], rect[1]) if rect else (0, 0)
    (ix, iy), (bx, by) = parts(img, box)
    bw = box[2] - box[0]
    bot.human_click((int(l + ix), int(t + iy)), jx=int(bw * 0.15), jy=2)
    time.sleep(np.random.uniform(0.2, 0.4))
    for ch in code:
        bot.keyboard.write(ch)
        time.sleep(np.random.uniform(0.08, 0.22))
    time.sleep(np.random.uniform(0.2, 0.4))
    bot.human_click((int(l + bx), int(t + by)), jx=int(bw * 0.2), jy=2)


def handle(bot, sct, rect, box, img):
    name = getattr(bot, "NOTIFY_NAME", "")
    was_running = bot.running or bot.retry_at is not None
    bot.running = False
    bot.retry_at = None
    try:
        bot.release_keys()
    except Exception:
        pass
    t0 = time.time()
    print("\n" + "!" * 56)
    print(" 🚨 매크로 방지 확인 창이 떴어요 — 봇을 멈췄습니다.")
    print("    숫자 4자리를 PC 에서 직접 입력하거나, 텔레그램으로 숫자를 보내주세요 (30초 안에)")
    print("!" * 56)
    log("확인 창 발견")
    _fails[0] = 0
    tg = _tg_ok(bot)
    if tg:
        # 제일 먼저 짧은 글 알림 (사진/답장 확인 준비보다 먼저 — 몇 초라도 빨리)
        _busy[0] = False
        _send_bg(bot, f"🚨🚨 [{name}] 매크로 방지 확인 창! 숫자 4자리를 보내주세요 (30초)")
    else:
        print("  [주의] 텔레그램 설정(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)이 비어 있어서 알림을 못 보냄"
              " — macro_guard.py 맨 위를 확인하세요")
        log("텔레그램 설정 없음 → 알림 못 보냄")
    save_png(img, "macro_debug.png")

    def cur():
        r = main_rect(bot) or rect
        im = grab(sct, r)
        return r, im, detect(im)

    base_id = 0
    if tg:
        u = _latest_update(bot)
        base_id = u[0] if u else 0
        x0, y0, x1, y1 = box
        crop = img[y0:y1, x0:x1]
        def _photo(c=crop):
            try:
                bot._send_telegram_photo(
                    f"🚨🚨 [{name}] 매크로 방지 확인 창! 숫자 4자리를 보내면 봇이 입력하고 [확인]을 누름"
                    f" (PC에서 직접 입력해도 됨)\n여러 대가 동시에 뜨면: 이 사진을 꾹 눌러 '답장'으로 숫자를"
                    f" 보내면 이 컴퓨터만 입력", jpeg_bytes(c, 2 if c.shape[1] < 500 else 1))
            except Exception as e:
                print(f"  (텔레그램 사진 전송 실패: {e})")
        threading.Thread(target=_photo, daemon=True).start()

    acked = False
    last_alert = time.time()
    n = 1
    gone_since = None
    while bot.alive and time.time() - t0 < GIVE_UP_SECS:
        now = time.time()
        if tg and not acked and now - t0 < ALERT_SECS and now - last_alert >= ALERT_EVERY \
                and now >= _hold_until[0]:
            n += 1
            last_alert = now
            left = max(0, int(30 - (now - t0)))
            _send_bg(bot, f"🚨 [{name}] 매크로 방지 창! 남은 약 {left}초 — 숫자 4자리 답장 ({n})")
        if tg:
            base_id, items = _new_updates(bot, base_id)
            mine = [t for t, rp in items if for_me(t, rp, name)]       # 다른 컴퓨터 것은 무시
            codes = [c for c in map(parse_code, mine) if c]
            if mine:
                code = codes[-1] if codes else None
                if code:
                    acked = True
                    r, im, b = cur()
                    if b is not None:
                        print(f"  텔레그램으로 받은 숫자 {code} 입력 → [확인]")
                        try:
                            enter_code(bot, r, b, im, code)
                        except Exception as e:
                            print(f"  (입력 실패: {e})")
                        time.sleep(1.5)
                        r, im, b = cur()
                        if b is not None:
                            _send(bot, f"⚠ [{name}] {code} 입력했는데 확인 창이 그대로예요 — 숫자를 다시 보내주세요",
                                  retry=True)
                            try:
                                bot._send_telegram_photo(f"[{name}] 지금 확인 창 (여러 대면 이 사진에 답장)",
                                                         jpeg_bytes(im[b[1]:b[3], b[0]:b[2]], 2))
                            except Exception:
                                pass
                elif any(mine):
                    if not acked:
                        _send(bot, f"[{name}] 알림 멈춤 — 숫자 4자리를 보내면 입력해요 (PC에서 직접 해도 됨)")
                    acked = True
        r, im, b = cur()
        if b is None:
            gone_since = gone_since or time.time()
            if time.time() - gone_since >= 1.5:
                break
        else:
            gone_since = None
        time.sleep(0.4)

    if gone_since is None or time.time() - gone_since < 1.5:
        print("[정지] 확인 창이 안 사라짐 — 봇은 멈춘 상태로 둡니다 (확인 후 F8)")
        if tg:
            _send(bot, f"🛑 [{name}] 매크로 방지 창이 안 풀렸어요 — 봇 정지 상태 (접속 끊겼을 수 있음)",
                  retry=True)
        return
    wait = np.random.uniform(*RESUME_WAIT)
    print(f"✅ 확인 창 사라짐 — {wait:.0f}초 뒤 이어서 진행")
    if tg:
        _send(bot, f"✅ [{name}] 매크로 방지 통과 — {wait:.0f}초 뒤 이어서 진행", retry=True)
    time.sleep(wait)
    if was_running and bot.alive and not bot.running:
        bot.running = True
        print("▶ 다시 시작")


def _watch(bot):
    import mss
    hits = 0
    with mss.mss() as sct:
        while bot.alive:
            time.sleep(CHECK_SEC)
            if not (bot.running or bot.retry_at is not None):
                hits = 0
                continue
            try:
                rect = main_rect(bot)
                img = grab(sct, rect)
                box = detect(img)
            except Exception:
                continue
            if box is None:
                hits = 0
                continue
            hits += 1
            if hits < 2:                       # 두 번 연속 보일 때만 (잘못 알아보는 것 방지) — 0.2초 뒤 바로 다시 봄
                time.sleep(0.2)
                try:
                    img2 = grab(sct, rect)
                    box2 = detect(img2)
                except Exception:
                    box2 = None
                if box2 is None:
                    hits = 0
                    continue
                img, box = img2, box2
            hits = 0
            try:
                handle(bot, sct, rect, box, img)
            except Exception as e:
                print(f"  (매크로 방지 처리 중 오류: {e})")


# ==================== 봇 연결 (식장이/주장이 공통) ====================

_tg_ctx = None


def _urlopen(url_or_req, data=None, timeout=30):
    import ssl
    import urllib.request
    import urllib.error
    global _tg_ctx
    try:
        return urllib.request.urlopen(url_or_req, data=data, timeout=timeout, context=_tg_ctx)
    except urllib.error.URLError as e:
        if _tg_ctx is None and isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            _tg_ctx = ssl._create_unverified_context()      # 보안프로그램 HTTPS 검사 대응
            return urllib.request.urlopen(url_or_req, data=data, timeout=timeout, context=_tg_ctx)
        raise


class Bot:
    """봇 파일(auto_cook / ring_cycle)마다 다른 이름을 하나로 맞춰주는 연결."""

    def __init__(self, mod):
        self.__dict__["m"] = mod
        am = getattr(mod, "am", None)
        self.__dict__["am"] = am
        tok = getattr(mod, "TELEGRAM_TOKEN", "") or TELEGRAM_TOKEN
        cid = getattr(mod, "TELEGRAM_CHAT_ID", "") or TELEGRAM_CHAT_ID
        self.__dict__["TELEGRAM_TOKEN"] = tok
        self.__dict__["TELEGRAM_CHAT_ID"] = cid
        self.__dict__["NOTIFY_NAME"] = getattr(mod, "NOTIFY_NAME", "") or NOTIFY_NAME or "PC"

    def __getattr__(self, name):
        m, am = self.__dict__["m"], self.__dict__["am"]
        # 텔레그램 보내기는 항상 여기 것을 씀 — 봇 파일의 토큰이 비어 있어도 위에서 찾은 토큰으로 보냄
        if name == "_tg_urlopen":
            return _urlopen
        if name == "_send_telegram":
            return self._text
        if name == "_send_telegram_photo":
            return self._photo
        if hasattr(m, name):
            return getattr(m, name)
        if name == "release_keys":
            return lambda: None
        if name in ("human_click", "_gw") and am is not None:
            return getattr(am, name)
        if name == "keyboard":
            import keyboard
            return keyboard
        if name == "retry_at":
            return None
        raise AttributeError(name)

    def __setattr__(self, name, value):
        m, am = self.__dict__["m"], self.__dict__["am"]
        if name == "retry_at" and not hasattr(m, "retry_at"):
            return
        setattr(m, name, value)
        if name == "running" and am is not None:
            am.running = value

    def _text(self, text):
        import urllib.parse
        url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": self.TELEGRAM_CHAT_ID, "text": text}).encode()
        _urlopen(url, data=data, timeout=10)

    def _photo(self, caption, jpeg):
        import random
        import urllib.request
        b = "----guard" + str(random.randint(10 ** 9, 10 ** 10))
        f = lambda n, v: (f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n").encode()
        body = b"".join([f("chat_id", self.TELEGRAM_CHAT_ID), f("caption", caption[:1024]),
                         f"--{b}\r\n".encode(),
                         b'Content-Disposition: form-data; name="photo"; filename="p.jpg"\r\n'
                         b"Content-Type: image/jpeg\r\n\r\n", jpeg, b"\r\n", f"--{b}--\r\n".encode()])
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendPhoto", data=body)
        req.add_header("Content-Type", f"multipart/form-data; boundary={b}")
        _urlopen(req, timeout=30)


def check_telegram(bot):
    """켤 때 텔레그램에 실제로 닿는지 확인 (메시지는 안 보냄)."""
    try:
        r = json.loads(bot._tg_urlopen(f"https://api.telegram.org/bot{bot.TELEGRAM_TOKEN}/getMe",
                                       timeout=10).read().decode())
        if r.get("ok"):
            print(f" 텔레그램 연결 확인 ✓ (봇 @{r['result'].get('username')}, 알림 이름 [{bot.NOTIFY_NAME}])")
            log("시작: 텔레그램 연결 OK")
            return True
        print(f" [주의] 텔레그램 응답 이상: {r}")
    except Exception as e:
        print(f" [주의] 텔레그램 연결 안 됨: {e} — 토큰/인터넷 확인. 이대로면 매크로 창이 떠도 알림이 안 감")
        log(f"시작: 텔레그램 연결 실패 {e}")
    return False


def start(mod):
    bot = Bot(mod)
    threading.Thread(target=_watch, args=(bot,), daemon=True).start()
    print(" 매크로 방지 확인 창 감시 중 — 뜨면 봇을 멈추고 " +
          ("텔레그램으로 계속 알림" if _tg_ok(bot) else "알림 (텔레그램 설정이 없어서 화면에만)"))
    if _tg_ok(bot):
        threading.Thread(target=check_telegram, args=(bot,), daemon=True).start()


def selftest(mod):
    """지금 화면에 확인 창이 있는지 검사하고 macro_test.png 로 저장."""
    import mss
    bot = Bot(mod)
    with mss.mss() as sct:
        rect = main_rect(bot)
        img = grab(sct, rect)
    box = detect(img)
    save_png(img, "macro_test.png")
    print(f"조이톡 창: {rect if rect else '못 찾음 → 주 모니터 전체'}")
    print("확인 창: " + (f"있음 {box}" if box else "없음") + "  (macro_test.png 저장)")


# ==================== 연습 ====================

def practice(mod):
    """연습: 가짜 확인코드 그림을 텔레그램으로 보내고, 답장이 맞는지·몇 초 걸렸는지 알려줌 (클릭 안 함)."""
    import random
    bot = mod if isinstance(mod, Bot) else Bot(mod)
    from PIL import Image, ImageDraw, ImageFont
    name = getattr(bot, "NOTIFY_NAME", "")
    if not _tg_ok(bot):
        print("[중단] 텔레그램 설정(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)이 비어 있어요 — "
              "식장이는 auto_cook.py, 주장이는 macro_guard.py 맨 위에 넣기")
        return
    code = "".join(random.choice("0123456789") for _ in range(4))
    im = Image.new("RGB", (520, 300), (24, 26, 40))
    d = ImageDraw.Draw(im)
    try:
        big = ImageFont.truetype("arial.ttf", 110)
        small = ImageFont.truetype("malgun.ttf", 26)
    except Exception:
        big = small = ImageFont.load_default()
    d.text((20, 15), "매크로 방지 확인 (연습)", fill=(230, 230, 230), font=small)
    d.rectangle([60, 70, 460, 230], fill=(30, 30, 45))
    d.text((95, 85), code, fill=(240, 180, 230), font=big)
    d.line([70, 200, 450, 110], fill=(200, 200, 200), width=3)
    import io
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    u = _latest_update(bot)
    base_id = u[0] if u else 0
    print(f"연습 시작 — 텔레그램을 보고 숫자 4자리를 답장하세요 (정답 {code})")
    t0 = time.time()
    try:
        bot._send_telegram_photo(f"🧪🚨 [{name}] 매크로 방지 연습! 숫자 4자리를 보내세요 (30초)"
                                 f"\n여러 대로 연습할 땐 이 사진을 꾹 눌러 '답장'으로 보내기", buf.getvalue())
    except Exception as e:
        print(f"[중단] 텔레그램 사진 전송 실패: {e}")
        return
    n, last = 0, 0.0
    while time.time() - t0 < 40:
        now = time.time()
        if now - t0 < ALERT_SECS and now - last >= ALERT_EVERY and now >= _hold_until[0]:
            n += 1
            last = now
            _send(bot, f"🧪 [{name}] 연습 — 남은 약 {max(0, int(30 - (now - t0)))}초, 숫자 4자리 답장 ({n})")
        base_id, items = _new_updates(bot, base_id)
        mine = [t for t, rp in items if for_me(t, rp, name)]
        if mine:
            got = next((c for c in map(parse_code, reversed(mine)) if c), None)
            secs = time.time() - t0
            if got is None:
                _send(bot, f"🧪 [{name}] '{mine[-1]}' 받음 — 숫자 4자리가 아니에요. 다시 보내보세요")
                continue
            ok = got == code
            msg = (f"🧪 [{name}] {'✅ 맞음' if ok else '❌ 틀림 (정답 ' + code + ')'} — {secs:.1f}초 걸림"
                   + ("" if secs <= 30 else " (실제였으면 시간 초과)")
                   + "\n실제 상황이면 봇이 이 숫자를 입력하고 [확인]을 눌렀을 거예요")
            _send(bot, msg, retry=True)
            print(msg)
            return
        time.sleep(0.4)
    _send(bot, f"🧪 [{name}] 연습 — 40초 동안 답장이 없었어요")
    print("40초 동안 답장 없음")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    try:
        if os.path.exists(os.path.join(HERE, "auto_match.py")):
            import auto_match as _bot           # 주장이 폴더
        else:
            import auto_cook as _bot            # 식장이 폴더
        if len(sys.argv) > 1 and sys.argv[1] == "연습":
            practice(_bot)
        else:
            selftest(_bot)
    except Exception:
        import traceback
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
