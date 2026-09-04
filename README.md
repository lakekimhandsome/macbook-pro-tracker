# MacBook Pro Tracker

Apple 주문 결과 페이지의 표시 내용을 개인 배송 대시보드로 가져옵니다.

- 배포판: <https://apple.lakekim.com>
- 로컬 Flask판: `python app.py` 후 <http://127.0.0.1:5050>

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

GitHub Pages판은 `docs/index.html` 하나로 동작합니다. 주문 정보는 URL fragment를
통해 현재 브라우저로만 전달되고 `localStorage`에 저장됩니다.

