import json
import re
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2_000_000

APPLE_ORDER_URL = "https://secure.store.apple.com/kr/shop/order/list"
ORDER_PATTERN = re.compile(
    r"\b(?:W\d{9,11}|WR\d+|J\d+|\d{10}|[A-Z]{3}\d{7}|EF[A-Z0-9]{10})\b"
)
STATUS_PROGRESS = {
    "주문 접수": 10,
    "주문 처리 중": 30,
    "처리 중": 30,
    "출고 준비 중": 55,
    "출고됨": 75,
    "배송 중": 85,
    "배송 완료": 100,
    "픽업 준비 완료": 100,
}
RELEVANT_KEYS = (
    "order", "item", "product", "part", "config", "status", "delivery",
    "shipment", "tracking", "carrier", "price", "amount", "fulfillment",
)

# ponytail: one-person, process-local cache; use SQLite if persistence is needed.
latest_order = None


def _visible_lines(text):
    ignored = {
        "Apple", "스토어", "Mac", "iPad", "iPhone", "Watch", "Vision",
        "AirPods", "TV 및 홈", "엔터테인먼트", "액세서리", "고객지원",
        "대한민국", "개인정보 처리방침", "약관", "법적 고지", "사이트 맵",
    }
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and line not in ignored and line not in lines:
            lines.append(line)
    return lines


def _flatten_model(value, path=""):
    fields = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            fields.extend(_flatten_model(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            fields.extend(_flatten_model(child, f"{path}[{index}]"))
    elif value not in (None, "", False) and any(key in path.lower() for key in RELEVANT_KEYS):
        text = re.sub(r"<[^>]+>", " ", str(value))
        text = re.sub(r"\s+", " ", text).strip()
        if text and not text.startswith(("http://", "https://", "/templates/")):
            fields.append((path, text))
    return fields


def _first_matching(lines, words, default):
    return next((line for line in lines if any(word in line for word in words)), default)


def parse_apple_page(payload):
    source = str(payload.get("source", ""))
    host = (urlparse(source).hostname or "").lower()
    if host != "apple.com" and not host.endswith(".apple.com"):
        raise ValueError("Apple 페이지에서 실행한 결과만 가져올 수 있습니다.")

    text = str(payload.get("text", ""))
    if not text or len(text) > 1_000_000:
        raise ValueError("가져온 페이지 내용이 없거나 너무 큽니다.")

    lines = _visible_lines(text)
    if not any(word in text for word in ("주문", "배송", "픽업", "Order")):
        raise ValueError("주문 결과 페이지가 아닙니다. Apple에서 주문 조회를 먼저 완료하세요.")

    fields = []
    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        try:
            fields = _flatten_model(json.loads(model))
        except json.JSONDecodeError:
            pass

    order_match = ORDER_PATTERN.search(text.upper())
    product_name = _first_matching(
        lines,
        ("MacBook", "iPhone", "iPad", "Apple Watch", "AirPods", "Mac mini", "Mac Studio"),
        "Apple 주문 제품",
    )
    status = _first_matching(lines, tuple(STATUS_PROGRESS), "상태 확인됨")
    progress = next(
        (percent for label, percent in STATUS_PROGRESS.items() if label in status), 50
    )
    arrival = _first_matching(
        lines, ("도착", "배송 예정", "수령 예정", "배송일"), "Apple 주문 페이지에서 확인"
    )
    hardware_index = next(
        (index for index, line in enumerate(lines) if line.rstrip(":") == "하드웨어"), None
    )
    return {
        "order_number": order_match.group(0) if order_match else "화면에서 확인",
        "product_name": product_name,
        "status": status,
        "estimated_arrival": arrival,
        "progress": progress,
        "details": lines[hardware_index + 1:] if hardware_index is not None else lines,
        "fields": fields,
        "source_url": source,
    }


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/")
def index():
    bookmarklet = (
        "javascript:(()=>{const d={source:location.href,text:document.body.innerText,"
        "model:document.querySelector('#init_data')?.textContent||''},"
        "f=document.createElement('form'),i=document.createElement('input');"
        "f.method='POST';f.action='http://127.0.0.1:5050/import';"
        "i.type='hidden';i.name='payload';i.value=JSON.stringify(d);"
        "f.append(i);document.body.append(f);f.submit()})()"
    )
    return render_template(
        "index.html",
        order=latest_order,
        bookmarklet=bookmarklet,
        apple_order_url=APPLE_ORDER_URL,
    )


@app.route("/import", methods=["GET", "POST"])
def import_page():
    global latest_order
    if request.method == "GET":
        return redirect("/")
    try:
        latest_order = parse_apple_page(json.loads(request.form.get("payload", "")))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return f"가져오기 실패: {exc}", 400
    return redirect("/")


@app.post("/capture")
def capture():
    global latest_order
    try:
        latest_order = parse_apple_page(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(port=5050)
