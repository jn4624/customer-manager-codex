# Customer Manager 개발 규칙

## 프로젝트 개요
- FastAPI 진입점은 `main.py`이며 라우터는 `routers/auth.py`, `routers/customers.py`, `routers/dashboard.py`에 둔다.
- HTML 페이지 라우터는 `routers/pages.py`, 템플릿은 `templates/`에 둔다.
- 기존 SQLAlchemy 모델과 DB 연결을 재사용한다.
- `customer.db`는 로컬 고객/주문 데이터 원본이다. 경로를 임의로 바꾸거나 파일을 교체하지 않는다.

## Git 작업 규칙
- `main` 브랜치에서 직접 파일을 수정하거나 커밋하지 않는다. 작업 전에 `codex/<작업명>` 형식의 브랜치를 만든다.
- 커밋은 작업 브랜치에만 만든다. `main` 반영은 별도 검토와 병합 절차를 따른다.
- `.gitignore`에 Python 캐시, 테스트 산출물, 가상환경, 비밀 환경 파일 및 로컬 DB가 제외되어야 한다. `customer.db`는 저장소에 커밋하지 않는다.
- 기존 변경사항을 확인하고, 해당 작업과 무관한 파일이나 사용자 변경을 커밋에 포함하지 않는다.

## 실행
```bash
python3 -m pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```
서버 시작 시 `Base.metadata.create_all()`은 없는 테이블만 생성하며, `employees.password_hash` 컬럼이 없으면 nullable 컬럼만 추가한다. 기본 주소는 `http://127.0.0.1:8000`, API 문서는 `/docs`다.
인증 서명 키는 환경 변수 `JWT_SECRET_KEY`로 설정한다. `APP_ENV=production`에서는 서명 키가 32바이트 이상이어야 하고 `COOKIE_SECURE=true`여야 서버가 시작된다. 로컬 개발에서는 임시 키를 생성하므로 서버를 다시 시작하면 기존 토큰이 무효화된다. HTTPS 배포 시 `APP_ENV=production`, `JWT_SECRET_KEY`, `COOKIE_SECURE=true`를 설정한다.

## 테스트 및 확인
```bash
python3 -m compileall -q main.py models.py database.py
python3 -m pytest -q
uvicorn main:app --host 127.0.0.1 --port 8000
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/health
```
고객 API는 `/api/customers`에서 목록·검색·필터·페이지·등록·수정·삭제를 제공한다. 매출 요약은 `/api/dashboard/sales`, CSV 내보내기는 `/api/customers/export.csv`다.

## 데이터 및 스키마 금지 규칙
- `models.py`, `database.py`, `customer.db`를 먼저 확인하고 기존 코드를 우선 확장한다.
- 기존 테이블의 칼럼 삭제, 칼럼 타입 변경, 기존 데이터 삭제/초기화/덮어쓰기를 금지한다.
- 스키마 확장은 nullable 칼럼 또는 새 테이블만 허용한다. DB 변경 전 기존 데이터와 참조 관계를 보존한다.
- 인증 계정은 기존 `employees` 테이블을 사용하고 `password_hash` nullable 칼럼만 추가한다. 계정 정보를 별도 사용자 테이블에 중복 저장하지 않는다.
- 비밀번호 원문을 저장하거나 로그에 남기지 않는다. 인증 토큰은 만료가 설정된 JWT httpOnly 쿠키로 전달하며 서버 세션을 만들지 않는다.
- `Base.metadata.create_all()`을 사용해 기존 DB에 없는 테이블만 추가한다. 개발 편의를 이유로 DB 파일을 재생성하지 않는다.
- 의존성은 `requirements.txt`에서 관리한다. 로컬 파이썬 환경에 설치하며 가상환경을 만들지 않는다.
- 고객을 삭제할 때 연관 주문의 외래 키 제약을 우회하거나 주문 데이터를 함께 삭제하지 않는다.
- API 계약을 바꿀 때 요청/응답 모델과 `/docs` 동작을 함께 갱신한다.
