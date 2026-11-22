import io
import os
import threading
import time
import uuid
from flask import Flask, request, jsonify, render_template_string
from instagrapi import Client
from PIL import Image

app = Flask(__name__)

UPLOAD_DIR = "/tmp/group_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
GROUP_PHOTO_PATH = os.path.join(UPLOAD_DIR, "group_avatar.jpg")

DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"
)

WEB_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"
)

state_lock = threading.Lock()
stop_event = threading.Event()
msg_pause_event = threading.Event()
msg_pause_event.set()

bot_status = {
    "running": False,
    "last_error": "",
    "msg_count": 0,
    "meta_checks": 0,
    "last_action": "Oprit",
}

bot_config = {
    "session_id": "",
    "proxy": "",
    "group_target": "",
    "message_text": "",
    "msg_delay": 4.0,
    "group_title": "",
    "meta_delay": 5.0,
    "protect_title": True,
    "protect_photo": False,
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kise Cagulă — Control Panel</title>
  <style>
    body { font-family: Arial, sans-serif; background: #111; color: #f2f2f2; margin: 0; padding: 16px; }
    .card { max-width: 560px; margin: auto; background: #1b1b1b; border: 1px solid #2e2e2e; border-radius: 10px; padding: 16px; }
    h2 { margin-top: 0; }
    label { display: block; font-size: 13px; margin-top: 10px; color: #ccc; }
    input[type="text"], input[type="password"], input[type="number"], textarea {
      width: 100%; box-sizing: border-box; margin-top: 4px; padding: 8px;
      background: #101010; color: #fff; border: 1px solid #383838; border-radius: 6px;
    }
    .row { display: flex; gap: 10px; }
    .row > div { flex: 1; }
    .checks { display: flex; gap: 16px; margin-top: 10px; font-size: 14px; }
    .btns { display: flex; gap: 10px; margin-top: 16px; }
    button { flex: 1; padding: 11px; border: none; border-radius: 7px; font-weight: bold; cursor: pointer; }
    .btn-start { background: #1f9d55; color: #fff; }
    .btn-stop { background: #c53030; color: #fff; }
    .status-box { margin-top: 14px; padding: 10px; background: #131313; border-radius: 7px; font-size: 13px; line-height: 1.5; }
    .badge-on { color: #48bb78; font-weight: bold; }
    .badge-off { color: #f56565; font-weight: bold; }
    .hint { font-size: 12px; color: #9ca3af; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>🪽 Kise Cagulă</h2>

    <form id="botForm" enctype="multipart/form-data">
      <label>Session ID Instagram</label>
      <input type="password" name="session_id" required placeholder="sessionid..." />

      <label>Proxy (opțional, ex. ip:port:user:pass sau http://user:pass@ip:port)</label>
      <input type="text" name="proxy" placeholder="" />

      <label>Nume grup (sau Thread ID)</label>
      <input type="text" name="group_target" required placeholder="Numele exact al grupului..." />

      <label>Mesaj automat</label>
      <textarea name="message_text" rows="2" placeholder="Textul trimis în grup..."></textarea>

      <div class="row">
        <div>
          <label>Delay mesaje (sec, min 4.0)</label>
          <input type="text" name="msg_delay" value="4.0" />
        </div>
        <div>
          <label>Delay nume/poză (1–120 sec)</label>
          <input type="text" name="meta_delay" value="5.0" />
        </div>
      </div>

      <label>Nume grup dorit (dacă lași gol, îl păstrează pe cel de sus)</label>
      <input type="text" name="group_title" placeholder="Numele grupului..." />

      <label>Poză grup (opțional, se convertește automat în JPG 800x800)</label>
      <input type="file" name="group_photo" accept="image/*" />

      <div class="checks">
        <label><input type="checkbox" name="protect_title" checked /> Menține nume</label>
        <label><input type="checkbox" name="protect_photo" /> Menține poză</label>
      </div>

      <div class="btns">
        <button type="button" class="btn-start" onclick="startBot()">START</button>
        <button type="button" class="btn-stop" onclick="stopBot()">STOP</button>
      </div>
      <div class="hint">Comenzi în grup când botul rulează: <b>.start 4</b> (pornește/setează delay mesaje) și <b>.stop</b> (pune mesajele pe pauză).</div>
    </form>

    <div class="status-box" id="statusBox">Se încarcă statusul...</div>
  </div>

  <script>
    async function startBot() {
      const form = document.getElementById("botForm");
      const data = new FormData(form);
      const res = await fetch("/start", { method: "POST", body: data });
      const json = await res.json();
      if (!res.ok) alert(json.error || "Eroare la pornire");
      refreshStatus();
    }

    async function stopBot() {
      await fetch("/stop", { method: "POST" });
      refreshStatus();
    }

    async function refreshStatus() {
      const res = await fetch("/status");
      const s = await res.json();
      const badge = s.running
        ? '<span class="badge-on">ACTIV</span>'
        : '<span class="badge-off">OPRIT</span>';
      document.getElementById("statusBox").innerHTML = `
        <div>Stare: ${badge}</div>
        <div>Mesaje trimise: <b>${s.msg_count}</b> | Verificări grup: <b>${s.meta_checks}</b></div>
        <div>Ultima acțiune: ${s.last_action || "-"}</div>
        <div>Ultima eroare: ${s.last_error || "Niciuna"}</div>
      `;
    }

    refreshStatus();
    setInterval(refreshStatus, 3000);
  </script>
</body>
</html>
"""


def normalize_proxy(proxy: str) -> str:
    p = (proxy or "").strip()
    if not p:
        return ""
    if "://" in p:
        return p
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"http://{user}:{pwd}@{ip}:{port}"
    return f"http://{p}"


def parse_float_safe(value, default_val: float, min_val: float, max_val: float) -> float:
    try:
        cleaned = str(value or "").replace(",", ".").strip()
        num = float(cleaned)
    except ValueError:
        num = default_val
    return min(max_val, max(min_val, num))


def build_client(session_id: str, proxy: str) -> Client:
    cl = Client()
    cl.set_user_agent(DEFAULT_UA)
    formatted_proxy = normalize_proxy(proxy)
    if formatted_proxy:
        cl.set_proxy(formatted_proxy)
    cl.login_by_sessionid(session_id)
    if hasattr(cl, "private") and getattr(cl.private, "headers", None) is not None:
        cl.private.headers["User-Agent"] = DEFAULT_UA
    return cl


def resolve_thread_id(cl: Client, group_target: str) -> int:
    target = (group_target or "").strip()
    if not target:
        raise ValueError("Nu ai introdus numele sau ID-ul grupului.")
    if target.isdigit():
        return int(target)

    threads = cl.direct_threads(amount=30)
    target_lower = target.lower()

    for t in threads:
        title = (getattr(t, "thread_title", None) or getattr(t, "title", None) or "").strip()
        if title.lower() == target_lower:
            return int(t.id)

    for t in threads:
        title = (getattr(t, "thread_title", None) or getattr(t, "title", None) or "").strip()
        if target_lower in title.lower():
            return int(t.id)

    raise ValueError(f"Nu am găsit niciun grup cu numele '{target}' în ultimele 30 conversații.")


def save_processed_photo(file_storage) -> str:
    raw_bytes = file_storage.read()
    with Image.open(io.BytesIO(raw_bytes)) as img:
        rgb_img = img.convert("RGB")
        squared = rgb_img.resize((800, 800), Image.Resampling.LANCZOS)
        squared.save(GROUP_PHOTO_PATH, format="JPEG", quality=85, optimize=True)
    return GROUP_PHOTO_PATH


def set_group_photo_compat(cl: Client, thread_id: int, photo_path: str) -> None:
    if hasattr(cl, "direct_thread_update_photo"):
        cl.direct_thread_update_photo(thread_id, photo_path)
        return
    if hasattr(cl, "direct_thread_change_photo"):
        cl.direct_thread_change_photo(thread_id, photo_path)
        return
    raise RuntimeError("Metoda de schimbare poză grup nu este disponibilă în această versiune instagrapi.")


def set_group_title_compat(cl: Client, thread_id: int, title: str) -> None:
    if hasattr(cl, "direct_thread_update_title"):
        cl.direct_thread_update_title(thread_id, title)
        return
    if hasattr(cl, "direct_thread_change_title"):
        cl.direct_thread_change_title(thread_id, title)
        return
    raise RuntimeError("Metoda de schimbare nume grup nu este disponibilă în această versiune instagrapi.")


def send_web_broadcast(cl: Client, thread_id: int, text: str) -> None:
    cookies = getattr(cl, "cookie_dict", {}) or {}
    csrf = cookies.get("csrftoken") or getattr(cl, "csrftoken", "") or ""
    session_http = getattr(cl, "private", None)
    if session_http is None or not hasattr(session_http, "post"):
        raise RuntimeError("Sesiunea HTTP internă nu este disponibilă.")

    headers = {
        "User-Agent": WEB_UA,
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/direct/inbox/",
        "Origin": "https://www.instagram.com",
    }
    if csrf:
        headers["X-CSRFToken"] = csrf

    payload = {
        "action": "send_item",
        "client_context": str(uuid.uuid4().int)[:19],
        "thread_ids": f"[{thread_id}]",
        "text": text,
    }

    resp = session_http.post(
        "https://i.instagram.com/api/v1/direct_v2/threads/broadcast/text/",
        data=payload,
        headers=headers,
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(resp.text)


def send_message_cascade(cl: Client, thread_id: int, text: str) -> str:
    errors = []

    try:
        send_web_broadcast(cl, thread_id, text)
        return "web_broadcast"
    except Exception as exc:
        errors.append(f"web_broadcast: {exc}")

    try:
        cl.direct_send(text, thread_ids=[thread_id])
        return "direct_send"
    except Exception as exc:
        errors.append(f"direct_send: {exc}")

    if hasattr(cl, "direct_answer"):
        try:
            cl.direct_answer(thread_id, text)
            return "direct_answer"
        except Exception as exc:
            errors.append(f"direct_answer: {exc}")

    csrf = ""
    try:
        csrf = getattr(cl, "csrftoken", "") or cl.cookie_dict.get("csrftoken", "")
    except Exception:
        csrf = ""

    client_ctx = str(uuid.uuid4().int)[:19]
    try:
        cl.private_request(
            "direct_v2/threads/broadcast/text/",
            data={
                "action": "send_item",
                "is_shh_mode": "0",
                "send_attribution": "inbox",
                "client_context": client_ctx,
                "thread_ids": f"[{thread_id}]",
                "text": text,
                "_uuid": getattr(cl, "uuid", str(uuid.uuid4())),
                "_csrftoken": csrf,
            },
        )
        return "private_broadcast_text"
    except Exception as exc:
        errors.append(f"broadcast_text: {exc}")

    try:
        cl.private_request(
            "direct_v2/threads/broadcast/text/",
            data={
                "action": "send_item",
                "client_context": str(uuid.uuid4().int)[:19],
                "thread_id": str(thread_id),
                "text": text,
                "_uuid": getattr(cl, "uuid", str(uuid.uuid4())),
                "_csrftoken": csrf,
            },
        )
        return "private_broadcast_single"
    except Exception as exc:
        errors.append(f"broadcast_single: {exc}")

    raise RuntimeError(" | ".join(errors))


def process_chat_commands(cl: Client, thread_id: int, seen_msg_ids: set) -> None:
    try:
        msgs = cl.direct_messages(thread_id, amount=5)
    except Exception:
        return

    for m in reversed(msgs):
        msg_id = str(getattr(m, "id", "") or "")
        if not msg_id or msg_id in seen_msg_ids:
            continue
        seen_msg_ids.add(msg_id)

        body = (getattr(m, "text", None) or "").strip().lower()
        if not body:
            continue

        if body == ".stop":
            msg_pause_event.clear()
            with state_lock:
                bot_status["last_action"] = "Comandă .stop primită din grup (mesaje pe pauză)"
        elif body.startswith(".start"):
            parts = body.split()
            if len(parts) >= 2:
                new_delay = parse_float_safe(parts[1], bot_config["msg_delay"], 4.0, 3600.0)
                with state_lock:
                    bot_config["msg_delay"] = new_delay
                bot_status_action = f"Comandă .start primită (delay {new_delay}s)"
            else:
                bot_status_action = "Comandă .start primită din grup"
            msg_pause_event.set()
            with state_lock:
                bot_status["last_action"] = bot_status_action


def spam_worker(cfg: dict, thread_id: int) -> None:
    if not cfg["message_text"].strip():
        return
    try:
        cl = build_client(cfg["session_id"], cfg["proxy"])
    except Exception as exc:
        with state_lock:
            bot_status["last_error"] = f"Eroare login mesaje: {exc}"
        return

    text = cfg["message_text"]
    seen_msg_ids = set()

    while not stop_event.is_set():
        process_chat_commands(cl, thread_id, seen_msg_ids)

        if not msg_pause_event.is_set():
            if stop_event.wait(1.0):
                break
            continue

        with state_lock:
            base_delay = bot_config["msg_delay"]

        current_wait = base_delay
        try:
            method_used = send_message_cascade(cl, thread_id, text)
            with state_lock:
                bot_status["msg_count"] += 1
                bot_status["last_action"] = f"Mesaj trimis (#{bot_status['msg_count']}) via {method_used}"
                bot_status["last_error"] = ""
        except Exception as exc:
            current_wait = max(base_delay, 12.0)
            with state_lock:
                bot_status["last_error"] = f"Eroare mesaj: {exc}"

        if stop_event.wait(current_wait):
            break


def group_meta_worker(cfg: dict, thread_id: int) -> None:
    if not cfg["protect_title"] and not cfg["protect_photo"]:
        return
    try:
        cl = build_client(cfg["session_id"], cfg["proxy"])
    except Exception as exc:
        with state_lock:
            bot_status["last_error"] = f"Eroare login grup: {exc}"
        return

    delay = cfg["meta_delay"]
    desired_title = (
        cfg["group_title"].strip()
        or (cfg["group_target"].strip() if not cfg["group_target"].strip().isdigit() else "")
    )

    while not stop_event.is_set():
        try:
            thread = cl.direct_thread(thread_id)
            current_title = getattr(thread, "thread_title", None) or getattr(thread, "title", None) or ""

            if cfg["protect_title"] and desired_title and current_title != desired_title:
                set_group_title_compat(cl, thread_id, desired_title)
                with state_lock:
                    bot_status["last_action"] = f"Nume grup restaurat: {desired_title}"

            if cfg["protect_photo"] and os.path.exists(GROUP_PHOTO_PATH):
                set_group_photo_compat(cl, thread_id, GROUP_PHOTO_PATH)
                with state_lock:
                    bot_status["last_action"] = "Poză grup verificată/actualizată"

            with state_lock:
                bot_status["meta_checks"] += 1
                bot_status["last_error"] = ""
        except Exception as exc:
            with state_lock:
                bot_status["last_error"] = f"Eroare grup meta: {exc}"

        if stop_event.wait(delay):
            break


def controller_loop(cfg: dict) -> None:
    try:
        lookup_client = build_client(cfg["session_id"], cfg["proxy"])
        thread_id = resolve_thread_id(lookup_client, cfg["group_target"])
        with state_lock:
            bot_status["last_action"] = f"Grup găsit (ID: {thread_id})"
    except Exception as exc:
        with state_lock:
            bot_status["running"] = False
            bot_status["last_error"] = f"Eroare găsire grup: {exc}"
            bot_status["last_action"] = "Oprit"
        return

    threads = []
    if cfg["message_text"].strip():
        t_msg = threading.Thread(target=spam_worker, args=(cfg, thread_id), daemon=True)
        t_msg.start()
        threads.append(t_msg)

    if cfg["protect_title"] or cfg["protect_photo"]:
        t_meta = threading.Thread(target=group_meta_worker, args=(cfg, thread_id), daemon=True)
        t_meta.start()
        threads.append(t_meta)

    while not stop_event.is_set():
        if threads and all(not t.is_alive() for t in threads):
            break
        time.sleep(1)

    with state_lock:
        bot_status["running"] = False
        if not bot_status["last_error"]:
            bot_status["last_action"] = "Oprit"


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/status", methods=["GET"])
def status():
    with state_lock:
        return jsonify(bot_status)


@app.route("/start", methods=["POST"])
def start():
    session_id = (request.form.get("session_id") or "").strip()
    group_target = (request.form.get("group_target") or "").strip()
    if not session_id or not group_target:
        return jsonify({"error": "Session ID și numele/ID-ul grupului sunt obligatorii."}), 400

    photo_file = request.files.get("group_photo")
    photo_saved = False
    if photo_file and photo_file.filename:
        save_processed_photo(photo_file)
        photo_saved = True

    protect_photo = bool(request.form.get("protect_photo"))
    if protect_photo and not (photo_saved or os.path.exists(GROUP_PHOTO_PATH)):
        return jsonify({"error": "Bifează 'Menține poză' doar după ce încarci o imagine."}), 400

    with state_lock:
        if bot_status["running"]:
            return jsonify({"error": "Botul rulează deja."}), 400

        bot_config.update({
            "session_id": session_id,
            "proxy": (request.form.get("proxy") or "").strip(),
            "group_target": group_target,
            "message_text": request.form.get("message_text") or "",
            "msg_delay": parse_float_safe(request.form.get("msg_delay"), 4.0, 4.0, 3600.0),
            "group_title": (request.form.get("group_title") or "").strip(),
            "meta_delay": parse_float_safe(request.form.get("meta_delay"), 5.0, 1.0, 120.0),
            "protect_title": bool(request.form.get("protect_title")),
            "protect_photo": protect_photo,
        })

        msg_pause_event.set()
        stop_event.clear()
        bot_status["running"] = True
        bot_status["last_error"] = ""
        bot_status["msg_count"] = 0
        bot_status["meta_checks"] = 0
        bot_status["last_action"] = "Se caută grupul..."

        cfg_copy = dict(bot_config)

    threading.Thread(target=controller_loop, args=(cfg_copy,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop():
    stop_event.set()
    msg_pause_event.set()
    with state_lock:
        bot_status["running"] = False
        bot_status["last_action"] = "Oprit manual"
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
