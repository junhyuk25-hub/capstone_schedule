from datetime import date, datetime
from html import escape
from time import sleep
from types import SimpleNamespace
import httpx
import secrets
import streamlit as st
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager


# ==================================================
# 기본 설정
# ==================================================
st.set_page_config(
    page_title="학업 일정 관리 시스템",
    page_icon="📅",
    layout="wide"
)

# 이전 URL 메뉴 파라미터 제거
if "menu" in st.query_params:
    del st.query_params["menu"]
# ==================================================
# 브라우저 로그인 유지용 암호화 쿠키
# ==================================================
try:
    cookie_password = st.secrets["COOKIES_PASSWORD"]

    if not isinstance(cookie_password, str) or len(cookie_password) < 32:
        raise ValueError("쿠키 암호화 키가 너무 짧습니다.")

except Exception:
    st.error(
        "쿠키 암호화 키 설정이 없습니다. "
        ".streamlit/secrets.toml을 확인해주세요."
    )
    st.stop()

cookies = EncryptedCookieManager(
    prefix="capstone_schedule/",
    password=cookie_password
)

# 브라우저 쿠키 정보를 불러올 때까지 대기
if not cookies.ready():
    st.stop()

# ==================================================
# 앱 서버 실행 식별자
# 서버를 완전히 종료하고 재실행하면 새 값 생성
# ==================================================
@st.cache_resource
def get_server_run_id():
    return secrets.token_hex(16)


SERVER_RUN_ID = get_server_run_id()

# ==================================================
# 브라우저 세션 확인
# 새로고침 시 유지, 탭 종료 시 초기화
# ==================================================
BROWSER_SESSION_JS = """
export default function(component) {
    const { data, setStateValue } = component;
    const storageKey = "capstone_schedule/browser_login";

    try {
        if (data.clear_requested) {
            sessionStorage.removeItem(storageKey);
        } else if (data.logged_in) {
            sessionStorage.setItem(storageKey, data.server_id);
        }

        const active = (
            sessionStorage.getItem(storageKey) === data.server_id
        );

        setStateValue("active", active);
    } catch (error) {
        setStateValue("active", false);
    }
}
"""

browser_session_component = st.components.v2.component(
    "capstone_browser_session_guard",
    js=BROWSER_SESSION_JS
)

browser_session_result = browser_session_component(
    key="capstone_browser_session_guard",
    data={
        "server_id": SERVER_RUN_ID,
        "logged_in": bool(
            st.session_state.get("auth_access_token")
            and st.session_state.get("auth_refresh_token")
        ),
        "clear_requested": bool(
            st.session_state.get("browser_session_clear_requested", False)
        ),
    },
    on_active_change=lambda: None
)

# 브라우저 확인 결과가 아직 없으면 인증 진행 중단
if browser_session_result.active is None:
    st.stop()

browser_session_active = browser_session_result.active

# 배경색, 글자색, 테두리색, 아이콘, 처리 결과 문구
NOTICE_THEMES = {
    "register": ("#EAF8EF", "#15803D", "#B8E5C8", "check-circle", "일정이 정상적으로 등록되었습니다."),
    "edit": ("#EFF6FF", "#2563EB", "#BFDBFE", "pencil", "일정이 수정되었습니다."),
    "delete": ("#FEF2F2", "#DC2626", "#FECACA", "trash", "일정이 삭제되었습니다."),
    "complete": ("#F0FDFA", "#0F766E", "#99E1D7", "check-check", "일정이 완료 처리되었습니다."),
    "undo": ("#FFFBEB", "#B45309", "#F3D49C", "undo", "일정의 완료가 취소되었습니다."),
    "warning": ("#FFFBEB", "#92400E", "#F3D49C", "warning", ""),
    "error": ("#FEF2F2", "#B91C1C", "#FECACA", "error", ""),
    "info": ("#EFF6FF", "#1D4ED8", "#BFDBFE", "info", ""),
}

# ==================================================
# 알림별 단색 SVG 아이콘
# ==================================================
NOTICE_ICON_PATHS = {
    "check-circle": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="m8 12 2.5 2.5L16 9"/>'
    ),
    "pencil": (
        '<path d="M12 20h9"/>'
        '<path d="m16 4 4 4-12 12-5 1 1-5z"/>'
    ),
    "trash": (
        '<path d="M3 6h18M8 6V4h8v2"/>'
        '<path d="M6 6l1 15h10l1-15M10 10v7M14 10v7"/>'
    ),
    "check-check": (
        '<path d="m4 12 4 4 6-6"/>'
        '<path d="m12 16 2 2 7-7"/>'
    ),
    "undo": (
        '<path d="M3 7v6h6"/>'
        '<path d="M3 13a9 9 0 1 1 3 6"/>'
    ),
    "warning": (
        '<path d="M10.3 3.5 2 18a2 2 0 0 0 1.7 3h16.6'
        'a2 2 0 0 0 1.7-3L13.7 3.5a2 2 0 0 0-3.4 0z"/>'
        '<path d="M12 9v4M12 17h.01"/>'
    ),
    "error": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="m9 9 6 6M15 9l-6 6"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M12 11v5M12 8h.01"/>'
    ),
}


def svg_notice_icon(icon_name, color, size=20):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true">'
        f'{NOTICE_ICON_PATHS[icon_name]}'
        '</svg>'
    )
def schedule_target(subject, schedule_name):
    """등록된 실제 과목명과 일정명으로 알림 대상을 표시한다."""
    return f"{str(subject).strip()} - {str(schedule_name).strip()}"


def notice_html(kind, message, full_width=False, size="normal"):
    """알림 종류별 단색 SVG 아이콘과 공통 디자인."""
    bg, color, border, icon_name, _ = NOTICE_THEMES[kind]
    width = "100%" if full_width else "auto"
    safe_message = escape(str(message))


    role = "alert" if kind == "error" else "status"

    # 일정 목록 제목 옆 알림만 위치 보정
    position_css = (
        "margin-left:-14px;transform:translateY(2px);"
        if size == "header" else ""
    )

    if size == "header":
        gap = "12px"
        min_height = "46px"
        padding = "10px 18px"
        font_size = "16px"
        icon_box = "22px"
        icon_svg = 22
        border_radius = "10px"
    else:
        gap = "10px"
        min_height = "44px"
        padding = "12px 16px"
        font_size = "14px"
        icon_box = "20px"
        icon_svg = 20
        border_radius = "8px"

    return (
        f'<div role="{role}" style="display:inline-flex;align-items:center;'
        f'{position_css}'
        f'gap:{gap};width:{width};max-width:100%;min-height:{min_height};'
        f'padding:{padding};box-sizing:border-box;'
        f'background:{bg};border:1px solid {border};border-radius:{border_radius};'
        f'color:{color};font-size:{font_size};font-weight:600;line-height:1.4;'
        'overflow-wrap:anywhere;vertical-align:middle;white-space:nowrap;">'
        f'<span aria-hidden="true" style="flex:0 0 {icon_box};'
        f'width:{icon_box};height:{icon_box};display:inline-flex;'
        'align-items:center;justify-content:center;">'
        f'{svg_notice_icon(icon_name, color, size=icon_svg)}'
        '</span>'
        f'<span style="min-width:0;">{safe_message}</span>'
        '</div>'
    )


def action_notice_html(kind, subject, schedule_name, full_width=False, size="normal"):
    """5개 일정 작업 결과: 실제 과목명 + 일정명 + 결과 문구."""
    message = f"{schedule_target(subject, schedule_name)} {NOTICE_THEMES[kind][4]}"
    return notice_html(kind, message, full_width=full_width, size=size)

# ==================================================
# Streamlit 기본 알림의 단색 아이콘
# ==================================================
_NATIVE_WARNING = st.warning
_NATIVE_ERROR = st.error
_NATIVE_INFO = st.info


def warning_notice(message):
    return _NATIVE_WARNING(
        message, icon=":material/warning:"
    )


def error_notice(message):
    return _NATIVE_ERROR(
        message, icon=":material/error:"
    )


def info_notice(message):
    return _NATIVE_INFO(
        message, icon=":material/info:"
    )


class StyledAlertSlot:
    def __init__(self):
        self.slot = st.empty()

    def warning(self, message):
        return self.slot.warning(
            message, icon=":material/warning:"
        )

    def error(self, message):
        return self.slot.error(
            message, icon=":material/error:"
        )

    def success(self, message):
        return self.slot.success(
            message, icon=":material/check_circle:"
        )

# ==================================================
# 브라우저 자동 번역 방지
# ==================================================
st.iframe(
    """
    <script>
        const doc = window.parent.document;

        // 한국어 페이지로 설정
        doc.documentElement.lang = "ko";

        // 자동 번역 억제
        doc.documentElement.setAttribute("translate", "no");
        doc.documentElement.classList.add("notranslate");

        if (doc.body) {
            doc.body.setAttribute("translate", "no");
        }

        // Google 번역 방지 메타 태그
        if (!doc.querySelector('meta[name="google"]')) {
            const meta = doc.createElement("meta");
            meta.name = "google";
            meta.content = "notranslate";
            doc.head.appendChild(meta);
        } else {
            doc.querySelector('meta[name="google"]')
               .setAttribute("content", "notranslate");
        }
    </script>
    """,
    height=1
)
# ==================================================
# 날짜 변경(자정) 시 D-Day 및 우선순위 화면 자동 갱신
# ==================================================
if "last_dday_update_date" not in st.session_state:
    st.session_state.last_dday_update_date = date.today()

@st.fragment(run_every="30s")
def refresh_after_date_change():
    today = date.today()

    # 날짜가 실제로 바뀌었을 때만 앱 전체를 다시 실행
    if st.session_state.last_dday_update_date != today:
        st.session_state.last_dday_update_date = today
        st.rerun()

refresh_after_date_change()


# ==================================================
# Supabase 인증 및 사용자별 데이터 접근
# ==================================================
# 주의: Supabase 클라이언트는 사용자별 실행에서 새로 만든다.
# st.cache_resource 등으로 인증된 클라이언트를 공유하지 않는다.
def new_supabase_client():
    client = st.session_state.get("supabase_client")

    if client is None:
        client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"],
        )
        st.session_state["supabase_client"] = client

    return client


# ==================================================
# 로그인 인증 쿠키 이름
# ==================================================
AUTH_COOKIE_KEYS = (
    "auth_access_token",
    "auth_refresh_token",
    "auth_login_expires_at",
    "selected_menu"
)


def clear_login_state():
    for key in (
        "auth_access_token",
        "auth_refresh_token",
        "auth_user_id",
        "auth_email",
        "supabase_client",
        "_verified_auth_client",
        "_verified_auth_refresh_token",
    ):
        st.session_state.pop(key, None)


def clear_auth_cookies():
    """브라우저에 저장된 로그인 인증 정보를 삭제한다."""
    changed = False

    for key in AUTH_COOKIE_KEYS:
        if key in cookies:
            del cookies[key]
            changed = True

    if changed:
        cookies.save()


def save_auth_session(auth_response, new_login=False):
    """Supabase 로그인 세션을 저장한다."""
    session = auth_response.session

    if (
        session is None
        or not session.access_token
        or not session.refresh_token
    ):
        raise ValueError("로그인 세션을 받지 못했습니다.")

    # Streamlit 세션에 인증 정보 저장
    st.session_state["auth_access_token"] = session.access_token
    st.session_state["auth_refresh_token"] = session.refresh_token

    if auth_response.user is not None:
        st.session_state["auth_user_id"] = str(auth_response.user.id)
        st.session_state["auth_email"] = auth_response.user.email or ""

    # 새 로그인 시 이전 로그아웃 요청 및 메뉴 초기화
    if new_login:
        st.session_state["browser_session_clear_requested"] = False
        st.session_state["active_schedule_menu"] = "대시보드"
        st.session_state["previous_menu"] = "대시보드"
        cookies["selected_menu"] = "dashboard"

    changed = bool(new_login)

    # 메뉴 변경값을 인증 정보와 함께 저장
    pending_menu = st.session_state.pop(
        "_pending_selected_menu", None
    )

    if (
        pending_menu is not None
        and cookies.get("selected_menu") != pending_menu
    ):
        cookies["selected_menu"] = pending_menu
        changed = True


    # 기존 7일 로그인 유지 쿠키 삭제
    if "auth_login_expires_at" in cookies:
        del cookies["auth_login_expires_at"]
        changed = True

    # 인증 토큰 저장 및 갱신
    if cookies.get("auth_access_token") != session.access_token:
        cookies["auth_access_token"] = session.access_token
        changed = True

    if cookies.get("auth_refresh_token") != session.refresh_token:
        cookies["auth_refresh_token"] = session.refresh_token
        changed = True

    if changed:
        cookies.save()

# ==================================================
# 로그인 버튼 클릭 시 인증 처리
# ==================================================
def handle_signin():
    email = str(st.session_state.get("signin_email", "")).strip()
    password = st.session_state.get("signin_password", "")

    st.session_state.pop("signin_feedback", None)

    if not email or not password:
        st.session_state["signin_feedback"] = (
            "warning", "이메일과 비밀번호를 입력해주세요."
        )
        return

    try:
        response = new_supabase_client().auth.sign_in_with_password({
            "email": email,
            "password": password,
        })


        session = response.session

        if (
            session is None
            or not session.access_token
            or not session.refresh_token
        ):
            raise ValueError("로그인 세션을 받지 못했습니다.")

        st.session_state["auth_access_token"] = session.access_token
        st.session_state["auth_refresh_token"] = session.refresh_token
        st.session_state["browser_session_clear_requested"] = False
        st.session_state["_pending_new_login"] = True


    except Exception:
        clear_login_state()
        st.session_state["signin_feedback"] = (
            "error",
            "로그인에 실패했습니다. 이메일 인증 여부와 입력 정보를 확인해주세요."
        )
def show_login_screen():
    st.title("📅 학업 일정 관리 시스템")
    st.caption("로그인하면 본인의 학업 일정만 조회하고 관리할 수 있습니다.")
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        with st.form("signin_form"):
            st.text_input("이메일", key="signin_email")
            st.text_input(
                "비밀번호", type="password", key="signin_password"
            )
            st.form_submit_button(
                "로그인", type="primary", on_click=handle_signin
            )

        signin_feedback = st.session_state.pop("signin_feedback", None)
        if signin_feedback:
            feedback_type, feedback_message = signin_feedback
            if feedback_type == "warning":
                warning_notice(feedback_message)
            else:
                error_notice(feedback_message)

    with signup_tab:
        with st.form("signup_form"):
            signup_email = st.text_input("이메일", key="signup_email").strip()
            signup_password = st.text_input(
                "비밀번호 (8자 이상)", type="password", key="signup_password"
            )
            signup_password_check = st.text_input(
                "비밀번호 확인", type="password", key="signup_password_check"
            )
            signup_clicked = st.form_submit_button("회원가입")

        if signup_clicked:
            if not signup_email or not signup_password:
                warning_notice("이메일과 비밀번호를 입력해주세요.")
            elif len(signup_password) < 8:
                warning_notice("비밀번호는 최소 8자 이상 입력해주세요.")
            elif signup_password != signup_password_check:
                warning_notice("비밀번호 확인이 일치하지 않습니다.")
            else:
                try:
                    response = new_supabase_client().auth.sign_up({
                        "email": signup_email,
                        "password": signup_password,
                    })

                    if response.session is not None:
                        signup_session = response.session

                        if (
                            not signup_session.access_token
                            or not signup_session.refresh_token
                        ):
                            raise ValueError("회원가입 세션을 받지 못했습니다.")

                        # 회원가입 직후에는 쿠키를 바로 저장하지 않음
                        st.session_state["auth_access_token"] = (
                            signup_session.access_token
                        )
                        st.session_state["auth_refresh_token"] = (
                            signup_session.refresh_token
                        )
                        st.session_state["browser_session_clear_requested"] = False
                        st.session_state["_pending_new_login"] = True

                        st.success(
                            "회원가입이 완료됐습니다. 로그인 상태로 전환합니다.",
                            icon=":material/check_circle:"
                        )
                        st.rerun()
                    else:
                        info_notice(
                            "가입 요청이 처리됐습니다. 이메일 인증 후 로그인해주세요."
                        )

                except Exception:
                    error_notice("회원가입에 실패했습니다. 입력 정보와 인증 설정을 확인해주세요.")
# 연결 값이 누락되면 안전하게 중단한다.
try:
    _config_url = st.secrets["SUPABASE_URL"]
    _config_key = st.secrets["SUPABASE_KEY"]
    if not _config_url or not _config_key:
        raise ValueError("빈 설정값")
except Exception:
    error_notice("Supabase 연결 정보가 없습니다. .streamlit/secrets.toml을 확인해주세요.")
    st.stop()

# ==================================================
# 로그인 화면 표시 영역
# ==================================================
login_screen_slot = st.empty()

# ==================================================
# 브라우저 세션 기준 로그인 복원
# ==================================================

# 사용자가 직접 로그아웃한 경우 인증 복원 차단
if st.session_state.get("browser_session_clear_requested", False):
    clear_auth_cookies()
    clear_login_state()

    with login_screen_slot.container():
        show_login_screen()

    st.stop()

# 새 브라우저 세션이나 서버 재시작 시
# 이전 인증 정보를 자동 복원하지 않는다.
if (
    not browser_session_active
    and not st.session_state.get("auth_access_token")
):
    clear_auth_cookies()
    clear_login_state()

# Streamlit 인증 상태가 없으면 브라우저 세션 확인
if (
    not st.session_state.get("auth_access_token")
    or not st.session_state.get("auth_refresh_token")
):
    cookie_access_token = cookies.get("auth_access_token")
    cookie_refresh_token = cookies.get("auth_refresh_token")

    if (
        browser_session_active
        and cookie_access_token
        and cookie_refresh_token
    ):
        st.session_state["auth_access_token"] = cookie_access_token
        st.session_state["auth_refresh_token"] = cookie_refresh_token

    else:
        clear_login_state()
        with login_screen_slot.container():
            show_login_screen()
        st.stop()


# ==================================================
# 인증 오류 기록: 실행.bat 터미널에 출력
# 토큰, 비밀번호 등 민감 정보는 출력하지 않음
# ==================================================
def log_auth_error(stage, error):
    error_code = getattr(error, "code", None)
    error_status = getattr(error, "status", None)

    # 오류 코드는 영문, 숫자, 밑줄만 출력
    if (
        not isinstance(error_code, str)
        or not error_code.replace("_", "").isalnum()
        or len(error_code) > 80
    ):
        error_code = "-"

    if not isinstance(error_status, int):
        error_status = "-"

    print(
        f"[인증오류] "
        f"시간={datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"단계={stage} "
        f"종류={type(error).__name__} "
        f"코드={error_code} "
        f"상태={error_status}",
        flush=True
    )


def reset_failed_authentication():
    st.session_state.pop("_pending_new_login", None)
    st.session_state["browser_session_clear_requested"] = True

    clear_login_state()

    try:
        clear_auth_cookies()
    except Exception as error:
        log_auth_error("인증 쿠키 삭제", error)


# ==================================================
# Supabase 서버에서 로그인 세션 검증
# ==================================================
auth_stage = "Supabase 클라이언트 준비"

try:
    db = new_supabase_client()
    auth_result = None

    # 이 클라이언트에서 이미 서버 인증을 완료했는지 확인
    reuse_verified_session = (
        st.session_state.get("_verified_auth_client") is db
        and st.session_state.get("_verified_auth_refresh_token")
        == st.session_state.get("auth_refresh_token")
        and bool(st.session_state.get("auth_user_id"))
        and not st.session_state.get("_pending_new_login", False)
    )

    # 이전에 검증한 세션은 재인증 없이 재사용
    if reuse_verified_session:
        auth_stage = "기존 로그인 세션 확인"

        current_session = db.auth.get_session()

        if (
            current_session is not None
            and current_session.user is not None
            and str(current_session.user.id)
            == st.session_state["auth_user_id"]
        ):
            auth_result = SimpleNamespace(
                session=current_session,
                user=current_session.user,
            )

    # 첫 로그인 또는 세션 복원 시 서버 인증 수행
    if auth_result is None:
        auth_stage = "로그인 세션 설정"

        auth_result = db.auth.set_session(
            st.session_state["auth_access_token"],
            st.session_state["auth_refresh_token"],
        )

    auth_stage = "사용자 인증 확인"

    verified_user = auth_result.user

    # 사용자 정보가 없을 경우에만 별도로 확인
    if verified_user is None:
        for attempt in range(1, 4):
            try:
                user_response = db.auth.get_user()
                verified_user = (
                    user_response.user
                    if user_response is not None
                    else None
                )
                break

            except (
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.RemoteProtocolError,
            ) as error:
                print(
                    f"[인증재시도] "
                    f"시간={datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"단계={auth_stage} "
                    f"종류={type(error).__name__} "
                    f"시도={attempt}/3",
                    flush=True
                )

                if attempt == 3:
                    raise

                sleep(0.5 * attempt)

    if verified_user is None:
        raise ValueError("사용자 검증 실패")

    if auth_result.session is None:
        raise ValueError("로그인 세션을 확인하지 못했습니다.")

    current_user_id = str(verified_user.id)

    st.session_state["auth_user_id"] = current_user_id
    st.session_state["auth_email"] = verified_user.email or ""

    # 다음 실행부터 동일 클라이언트의 검증된 세션 재사용
    st.session_state["_verified_auth_client"] = db
    st.session_state["_verified_auth_refresh_token"] = (
        auth_result.session.refresh_token
    )

except Exception as error:
    log_auth_error(auth_stage, error)

    error_code = getattr(error, "code", None)
    error_type = type(error).__name__

    # 인증 정보가 실제로 무효화되었다고 판단할 수 있는 오류
    invalid_session_codes = {
        "session_expired",
        "session_not_found",
        "refresh_token_not_found",
        "refresh_token_already_used",
        "invalid_refresh_token",
        "invalid_credentials",
        "bad_jwt",
        "invalid_jwt",
        "user_not_found",
    }

    invalid_session_types = {
        "AuthSessionMissingError",
        "AuthInvalidJwtError",
    }

    session_invalid = (
        error_code in invalid_session_codes
        or error_type in invalid_session_types
    )

    if session_invalid:
        reset_failed_authentication()

        info_notice(
            "로그인 세션이 만료되었거나 유효하지 않습니다. "
            "다시 로그인해주세요."
        )

        with login_screen_slot.container():
            show_login_screen()

        st.stop()

    # 통신 오류 등 원인이 불명확한 경우에는
    # 로그인 정보를 자동으로 삭제하지 않음
    error_notice(
        "로그인 인증을 확인하는 중 오류가 발생했습니다. "
        "로그인 정보는 삭제하지 않았습니다."
    )

    st.caption(
        "실행.bat 터미널의 [인증오류] 기록을 확인해주세요."
    )

    if st.button("인증 다시 확인", key="auth_retry"):
        st.rerun()

    if st.button("다시 로그인", key="auth_reset_login"):
        reset_failed_authentication()
        st.rerun()

    st.stop()


# ==================================================
# 사용자 검증 성공 후 쿠키 저장
# ==================================================
try:
    save_auth_session(
        auth_result,
        new_login=st.session_state.get(
            "_pending_new_login", False
        )
    )

except Exception as error:
    log_auth_error("인증 정보 및 쿠키 저장", error)

    error_notice(
        "로그인 정보 저장 중 오류가 발생했습니다. "
        "터미널 기록을 확인하고 다시 시도해주세요."
    )

    st.stop()

else:
    st.session_state.pop("_pending_new_login", None)



# 로그인 성공 후 이전 로그인 화면 제거
login_screen_slot.empty()

def logout_user():
    # Supabase 현재 세션 로그아웃
    try:
        db.auth.sign_out({"scope": "local"})
    except Exception:
        pass

    # 저장된 인증 쿠키 삭제
    clear_auth_cookies()

    # Streamlit 로그인 상태 삭제
    clear_login_state()

    # 브라우저 세션도 초기화하도록 요청
    st.session_state["browser_session_clear_requested"] = True

    # 로그인 입력값 초기화
    for key in (
        "signin_email", "signin_password", "signup_email",
        "signup_password", "signup_password_check",
    ):
        st.session_state.pop(key, None)

    st.rerun()


# ==================================================
# 로그아웃 확인 팝업
# ==================================================
@st.dialog("로그아웃 확인")
def confirm_logout_dialog():
    st.write("로그아웃 하시겠습니까?")

    cancel_col, confirm_col = st.columns(2)

    with cancel_col:
        if st.button(
            "취소",
            key="logout_cancel",
            width="stretch"
        ):
            st.rerun()

    with confirm_col:
        if st.button(
            "로그아웃",
            key="logout_confirm",
            type="primary",
            width="stretch"
        ):
            logout_user()
# ==================================================
# 일정 완료 처리 (현재 사용자 일정에만 적용)
# ==================================================
def complete_schedule(schedule_id):
    completed_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = (
        db.table("schedules")
        .update({"completed": True, "completed_at": completed_time})
        .eq("id", schedule_id)
        .eq("user_id", current_user_id)
        .eq("completed", False)
        .select("id")
        .execute()
    )
    return bool(result.data)


# ==================================================
# 일정 완료 취소 처리 (현재 사용자 일정에만 적용)
# ==================================================
def cancel_schedule_completion(schedule_id):
    result = (
        db.table("schedules")
        .update({"completed": False, "completed_at": None})
        .eq("id", schedule_id)
        .eq("user_id", current_user_id)
        .eq("completed", True)
        .select("id")
        .execute()
    )
    return bool(result.data)

# ==================================================
# D-Day 계산
# ==================================================
def calculate_dday(deadline):

    deadline_date = datetime.strptime(
        deadline,
        "%Y-%m-%d"
    ).date()

    return (
        deadline_date
        - date.today()
    ).days


# ==================================================
# 우선순위 계산
# ==================================================
def calculate_priority(dday, importance, expected_time):

    importance_score = {
        "높음": 30,
        "보통": 20,
        "낮음": 10
    }

    score = importance_score[importance]

    # D-Day 점수
    if dday < 0:
        score += 0

    elif dday == 0:
        score += 10

    elif dday <= 3:
        score += 8

    elif dday <= 7:
        score += 5

    else:
        score += 2

    # 예상 소요시간 점수
    if expected_time >= 8:
        score += 5

    elif expected_time >= 4:
        score += 3

    elif expected_time >= 2:
        score += 2

    else:
        score += 1

    return score

# ==================================================
# D-Day 표시
# ==================================================
def format_dday(dday):

    if dday > 0:
        return f"D-{dday}"

    elif dday == 0:
        return "D-Day"

    else:
        return f"D+{abs(dday)}"


# ==================================================
# 예상 소요시간 표시
# ==================================================
def format_expected_time(expected_time):

    hours = int(expected_time)

    return f"{hours}시간"


# ==================================================
# 현재 로그인 사용자의 일정 불러오기
# ==================================================
def load_schedules():
    try:
        response = (
            db.table("schedules")
            .select("id,subject,schedule_name,deadline,importance,expected_time,completed,completed_at")
            .eq("user_id", current_user_id)
            .order("id")
            .execute()
        )
    except Exception:
        error_notice("서버 연결 또는 일정 조회에 실패했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()
    rows = response.data or []
    schedules = []

    for row in rows:
        dday = calculate_dday(str(row["deadline"]))
        priority = calculate_priority(dday, row["importance"], row["expected_time"])
        schedules.append({
            "id": row["id"],
            "과목명": row["subject"],
            "일정명": row["schedule_name"],
            "마감일": str(row["deadline"]),
            "중요도": row["importance"],
            "예상 소요시간": row["expected_time"],
            "D-Day": dday,
            "우선순위 점수": priority,
            "완료 여부": bool(row["completed"]),
            "완료 일시": row["completed_at"],
        })

    schedules.sort(
        key=lambda x: (-x["우선순위 점수"], x["D-Day"], x["id"])
    )
    return schedules

# ==================================================
# 현재 로그인 사용자의 중복 일정 검사 (띄어쓰기 정리 포함)
# ==================================================
def is_duplicate_schedule(subject, schedule_name, deadline, exclude_id=None):
    normalized_subject = " ".join(subject.split())
    normalized_name = " ".join(schedule_name.split())
    deadline_text = deadline.strftime("%Y-%m-%d")

    try:
        response = (
            db.table("schedules")
            .select("id,subject,schedule_name")
            .eq("user_id", current_user_id)
            .eq("deadline", deadline_text)
            .execute()
        )
    except Exception:
        # 조회에 실패한 경우 중복 여부를 추측해 저장하지 않는다.
        error_notice("서버 연결 또는 중복 일정 확인에 실패했습니다. 다시 시도해주세요.")
        st.stop()
    for row in response.data or []:
        if exclude_id is not None and row["id"] == exclude_id:
            continue
        saved_subject = " ".join(row["subject"].split())
        saved_name = " ".join(row["schedule_name"].split())
        if normalized_subject == saved_subject and normalized_name == saved_name:
            return True
    return False

# ==================================================
# 예상 소요시간 상태 초기화
# ==================================================
if "time_hours" not in st.session_state:
    st.session_state.time_hours = 1

# ==================================================
# 시간 입력값 읽기
# ==================================================
def get_time_hours():

    try:

        hours_text = str(st.session_state.get(
            "hours_input_widget",
            st.session_state.get("hours_input", "")
        )).strip()

        hours = (
            int(hours_text)
            if hours_text
            else 0
        )

    except (ValueError, TypeError):

        hours = 0

    hours = max(
        0,
        min(100, hours)
    )

    return hours


# ==================================================
# 시간 +/- 처리
# ==================================================
def change_hours(amount):

    hours = get_time_hours()

    st.session_state.hours_warning = None

    # 100시간에서 + 버튼 클릭
    if amount > 0 and hours >= 100:

        st.session_state.hours_warning = (
            "예상 소요시간은 최대 100시간입니다. "
            "더 이상 시간을 증가시킬 수 없습니다."
        )

    # 1시간에서 - 버튼 클릭
    elif amount < 0 and hours <= 1:

        hours = 1

        st.session_state.hours_warning = (
            "예상 소요시간은 최소 1시간입니다. "
            "1시간으로 유지했습니다."
        )

    # 정상 범위
    else:

        raw_value = str(
            st.session_state.get("hours_input_widget", "")
        ).strip()

        try:
            entered_hours = int(raw_value)
        except (ValueError, TypeError):
            entered_hours = hours

        # 100시간 초과 입력 후 - 버튼을 누르면 100으로 변경
        if amount < 0 and entered_hours > 100:
            hours = 100

        else:
            hours = max(1, min(100, hours + amount))

    st.session_state.time_hours = hours
    st.session_state.hours_input = str(hours)
    st.session_state.hours_input_widget = str(hours)
    st.session_state.hours_input_invalid = False   


# ==================================================
# 예상 소요시간 직접 입력 검사
# ==================================================
def limit_hours_input():

    raw = str(
        st.session_state.get("hours_input_widget", "")
    ).strip()

    try:
        hours = int(raw)

    except (ValueError, TypeError):

        st.session_state.hours_input_invalid = True

        st.session_state.hours_warning = (
            "예상 소요시간은 숫자로 입력해주세요. "
            "1~100시간 사이로 다시 입력해주세요."
        )

        return

    # 최대 100시간 초과
    if hours > 100:

        st.session_state.hours_input_invalid = True

        st.session_state.hours_warning = (
            "예상 소요시간은 최대 100시간까지 입력할 수 있습니다. "
            "시간을 다시 입력해주세요."
        )

        return

    # 0시간 이하 입력
    if hours <= 0:

        st.session_state.hours_input_invalid = True

        st.session_state.hours_warning = (
            "예상 소요시간은 1~100시간 사이로 입력해주세요."
        )

        return

    # 정상적인 입력
    st.session_state.hours_input_invalid = False
    st.session_state.hours_warning = None

    st.session_state.hours_input = str(hours)
    st.session_state.time_hours = hours
# ==================================================
# 일정 수정: 예상 소요시간 검증
# ==================================================
def validate_edit_hours(schedule_id):
    input_key = f"edit_hours_input_{schedule_id}"
    warning_key = f"edit_hours_warning_{schedule_id}"
    invalid_key = f"edit_hours_invalid_{schedule_id}"

    raw = str(st.session_state.get(input_key, "")).strip()

    try:
        hours = int(raw)
    except (ValueError, TypeError):
        st.session_state[invalid_key] = True
        st.session_state[warning_key] = (
            "예상 소요시간은 숫자로 입력해주세요. "
            "1~100시간 사이로 다시 입력해주세요."
        )
        return

    if hours > 100:
        warning = (
            "예상 소요시간은 최대 100시간까지 입력할 수 있습니다. "
            "시간을 다시 입력해주세요."
        )

    elif hours <= 0:
        warning = (
            "예상 소요시간은 1~100시간 사이로 입력해주세요."
        )

    else:
        warning = None

    st.session_state[invalid_key] = warning is not None
    st.session_state[warning_key] = warning


# ==================================================
# 일정 수정: 예상 소요시간 +/- 처리
# ==================================================
def change_edit_hours(schedule_id, amount):
    input_key = f"edit_hours_input_{schedule_id}"
    warning_key = f"edit_hours_warning_{schedule_id}"
    invalid_key = f"edit_hours_invalid_{schedule_id}"

    try:
        entered = int(
            str(st.session_state.get(input_key, "")).strip()
        )
    except (ValueError, TypeError):
        entered = 0

    hours = max(0, min(100, entered))
    warning = None

    # 100 초과 입력 후 - 클릭 시 100으로 보정
    if amount < 0 and entered > 100:
        hours = 100

    # 100에서 + 클릭 시 증가 차단
    elif amount > 0 and hours >= 100:
        warning = (
            "예상 소요시간은 최대 100시간입니다. "
            "더 이상 시간을 증가시킬 수 없습니다."
        )

    # 1시간에서 - 클릭 시 감소 차단
    elif amount < 0 and hours <= 1:
        hours = 1
        warning = (
            "예상 소요시간은 최소 1시간입니다. "
            "1시간으로 유지했습니다."
        )

    else:
        hours = max(1, min(100, hours + amount))

    st.session_state[input_key] = str(hours)
    st.session_state[warning_key] = warning
    st.session_state[invalid_key] = False   
# ==================================================
# 일정 수정 팝업
# ==================================================
@st.dialog("일정 수정")
def edit_schedule_dialog(selected_schedule):

    st.write("선택한 학업 일정을 수정합니다.")

    edit_subject = st.text_input(
        "과목명",
        value=selected_schedule["과목명"]
    )

    edit_schedule_name = st.text_input(
        "일정명",
        value=selected_schedule["일정명"]
    )

    edit_deadline = st.date_input(
        "마감일",
        value=datetime.strptime(
            selected_schedule["마감일"],
            "%Y-%m-%d"
        ).date()
    )

    importance_options = ["높음", "보통", "낮음"]

    edit_importance = st.selectbox(
        "중요도",
        importance_options,
        index=importance_options.index(
            selected_schedule["중요도"]
        )
    )

    # 수정 대상의 저장된 예상 소요시간 불러오기
    schedule_id = selected_schedule["id"]

    edit_hours_key = f"edit_hours_input_{schedule_id}"
    edit_warning_key = f"edit_hours_warning_{schedule_id}"
    edit_invalid_key = f"edit_hours_invalid_{schedule_id}"

    if edit_hours_key not in st.session_state:
        st.session_state[edit_hours_key] = str(
            int(selected_schedule["예상 소요시간"])
        )

    # 예상 소요시간 입력창 및 +/- 버튼 디자인
    st.markdown("""
    <style>
    div[class*="st-key-edit_hours_input_"] [data-baseweb="input"] {
        height: 40px !important;
        min-height: 40px !important;
    }

    div[class*="st-key-edit_hours_input_"] input {
        height: 40px !important;
        font-size: 16px !important;
    }

    div[class*="st-key-edit_hour_minus_"] button,
    div[class*="st-key-edit_hour_plus_"] button {
        height: 40px !important;
        min-height: 40px !important;
        padding: 0 !important;
        border-radius: 6px !important;
    }

    div[class*="st-key-edit_hour_minus_"] button {
        background: #dc2626 !important;
        border-color: #dc2626 !important;
    }

    div[class*="st-key-edit_hour_minus_"] button:hover {
        background: #b91c1c !important;
        border-color: #b91c1c !important;
    }

    div[class*="st-key-edit_hour_plus_"] button {
        background: #2563eb !important;
        border-color: #2563eb !important;
    }

    div[class*="st-key-edit_hour_plus_"] button:hover {
        background: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
    }

    div[class*="st-key-edit_hour_minus_"] button p,
    div[class*="st-key-edit_hour_plus_"] button p {
        color: white !important;
        font-size: 24px !important;
        font-weight: 700 !important;
        line-height: 1 !important;
    }
        /* 일정 수정: 시간 입력창과 +/- 버튼 간격 6px */
    div[data-testid="stHorizontalBlock"]:has(
        [class*="st-key-edit_hour_minus_"]
    ) {
        gap: 6px !important;
    }

    /* -와 + 버튼 너비 48px */
    div[data-testid="stHorizontalBlock"]:has(
        [class*="st-key-edit_hour_minus_"]
    ) > div[data-testid="stColumn"]:not(:first-child) {
        flex: 0 0 48px !important;
        width: 48px !important;
        min-width: 48px !important;
        max-width: 48px !important;
    }

    /* 남은 공간은 숫자 입력창에 할당 */
    div[data-testid="stHorizontalBlock"]:has(
        [class*="st-key-edit_hour_minus_"]
    ) > div[data-testid="stColumn"]:first-child {
        flex: 1 1 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("**예상 소요시간**")

    edit_input_col, edit_minus_col, edit_plus_col = st.columns(
        [4, 0.9, 0.9],
        gap="small",
        vertical_alignment="center"
    )

    # 직접 입력
    with edit_input_col:
        st.text_input(
            "시간 입력",
            key=edit_hours_key,
            label_visibility="collapsed",
            on_change=validate_edit_hours,
            args=(schedule_id,)
        )

    # - 버튼
    with edit_minus_col:
        st.button(
            "−",
            key=f"edit_hour_minus_{schedule_id}",
            width="stretch",
            on_click=change_edit_hours,
            args=(schedule_id, -1)
        )

    # + 버튼
    with edit_plus_col:
        st.button(
            "+",
            key=f"edit_hour_plus_{schedule_id}",
            width="stretch",
            on_click=change_edit_hours,
            args=(schedule_id, 1)
        )

    st.caption("※ 1~100시간 입력 가능 (입력 후 Enter)")

    # 잘못된 입력값 경고
    if st.session_state.get(edit_warning_key):
        warning_notice(st.session_state[edit_warning_key])

    # 수정 저장에 사용할 예상 소요시간
    try:
        edit_expected_time = int(
            str(st.session_state[edit_hours_key]).strip()
        )
    except (ValueError, TypeError):
        edit_expected_time = 0

    st.write(
        f"현재 D-Day: "
        f"{format_dday(selected_schedule['D-Day'])}"
    )

    st.write(
        f"현재 우선순위 점수: "
        f"{selected_schedule['우선순위 점수']}"
    )

    if (
        st.button(
            "일정 수정",
            type="primary",
            on_click=validate_edit_hours,
            args=(schedule_id,)
        )
        and not st.session_state.get(edit_invalid_key, False)
    ):

        if not edit_subject.strip():
            warning_notice("과목명을 입력해주세요.")

        elif not edit_schedule_name.strip():
            warning_notice("일정명을 입력해주세요.")

        elif (
            edit_subject.strip() == selected_schedule["과목명"]
            and edit_schedule_name.strip() == selected_schedule["일정명"]
            and edit_deadline.strftime("%Y-%m-%d") == selected_schedule["마감일"]
            and edit_importance == selected_schedule["중요도"]
            and int(edit_expected_time) == int(selected_schedule["예상 소요시간"])
        ):
            warning_notice(
                "기존 일정과 동일합니다. "
                "수정할 내용을 변경해주세요."
            )
        # 일정 수정 시 중복 검사
        elif is_duplicate_schedule(
            edit_subject,
            edit_schedule_name,
            edit_deadline,
            exclude_id=selected_schedule["id"]
        ):

            warning_notice(
                f"{schedule_target(edit_subject, edit_schedule_name)} 일정이 이미 등록되어 있습니다. "
                "동일한 과목명, 일정명, 마감일이 존재합니다."
            )
        else:
            # 수정 시 대상 일정 ID와 로그인 사용자 ID를 모두 확인한다.
            try:
                updated = (
                    db.table("schedules")
                    .update({
                        "subject": edit_subject.strip(),
                        "schedule_name": edit_schedule_name.strip(),
                        "deadline": edit_deadline.strftime("%Y-%m-%d"),
                        "importance": edit_importance,
                        "expected_time": edit_expected_time,
                    })
                    .eq("id", selected_schedule["id"])
                    .eq("user_id", current_user_id)
                    .select("id")
                    .execute()
                )
            except Exception:
                error_notice(
                    f"{schedule_target(edit_subject, edit_schedule_name)} "
                    "일정 수정에 실패했습니다. 다시 시도해주세요."
                )
                return
            if not updated.data:
                error_notice(
                    f"{schedule_target(edit_subject, edit_schedule_name)} "
                    "일정 수정에 실패했습니다. 다시 시도해주세요."
                )
                return

            new_dday = (edit_deadline - date.today()).days
            new_priority = calculate_priority(
                new_dday, edit_importance, edit_expected_time
            )
            st.session_state["action_message"] = {
                "kind": "edit",
                "subject": edit_subject.strip(),
                "schedule_name": edit_schedule_name.strip(),
                "dday": new_dday,
                "priority": new_priority,
            }
            st.rerun()

    if st.button("취소"):
        st.rerun()

# ==================================================
# 일정 삭제 확인 팝업
# ==================================================
@st.dialog("일정 삭제 확인")
def delete_schedule_dialog(selected_schedule):

    st.write("선택한 일정을 삭제하시겠습니까?")

    st.write(
        f"**{selected_schedule['과목명']} - "
        f"{selected_schedule['일정명']}**"
    )

    warning_notice("삭제한 일정은 복구할 수 없습니다.")

    cancel_col, delete_col = st.columns(2)

    with cancel_col:
        if st.button("취소", width="stretch"):
            st.rerun()

    with delete_col:
        if st.button(
            "삭제",
            type="primary",
            width="stretch"
        ):

            try:
                deleted = (
                    db.table("schedules")
                    .delete()
                    .eq("id", selected_schedule["id"])
                    .eq("user_id", current_user_id)
                    .select("id")
                    .execute()
                )
            except Exception:
                error_notice(
                    f"{schedule_target(selected_schedule['과목명'], selected_schedule['일정명'])} "
                    "일정 삭제에 실패했습니다. 다시 시도해주세요."
                )
                return
            if not deleted.data:
                error_notice(
                    f"{schedule_target(selected_schedule['과목명'], selected_schedule['일정명'])} "
                    "일정 삭제에 실패했습니다. 다시 시도해주세요."
                )
                return

            st.session_state["action_message"] = {
                "kind": "delete",
                "subject": selected_schedule["과목명"],
                "schedule_name": selected_schedule["일정명"],
            }
            st.rerun()

# ==================================================
# 사이드바: 선택형 네비게이션 (기존 메뉴 값 및 기능 동일)
# ==================================================
# F5 새로고침 시 저장된 메뉴 복원
MENU_CODES = {
    "대시보드": "dashboard",
    "일정 등록": "register",
    "일정 목록 (완료·수정·삭제)": "list",
}

CODE_TO_MENU = {
    code: name for name, code in MENU_CODES.items()
}

if "active_schedule_menu" not in st.session_state:
    saved_menu = cookies.get("selected_menu", "dashboard")
    st.session_state.active_schedule_menu = CODE_TO_MENU.get(
        saved_menu, "대시보드"
    )

def set_schedule_menu(value):
    st.session_state.active_schedule_menu = value

    # 메뉴 저장을 예약하고 인증 처리 시 함께 저장
    st.session_state["_pending_selected_menu"] = MENU_CODES[value]

_nav_css = """
<style>
section[data-testid="stSidebar"] {
    background:#f5f8ff !important;
    border-right:1px solid #e1e8f3 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top:7px !important;
}
.schedule-brand {
    display:flex;align-items:center;gap:12px;
    padding:7px 0 18px;border-bottom:1px solid #dee7f5;
    white-space:nowrap;
}
.schedule-brand-icon {
    display:inline-flex;align-items:center;justify-content:center;
    width:35px;height:35px;background:#2364f3;color:#fff;
    border-radius:7px;font-size:23px;
}
.schedule-brand-name {font-size:16px;font-weight:800;color:#182b50;letter-spacing:-.6px;}
.schedule-menu-label {padding:20px 0 12px;font-size:14px;font-weight:700;color:#30415e;}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button {
    display:flex !important;align-items:center !important;justify-content:flex-start !important;
    text-align:left !important; gap:13px !important;
    border:none !important;box-shadow:none !important;background:transparent !important;
    color:#203353 !important;padding:10px 12px !important;
    min-height:47px !important;height:47px !important;
    border-radius:10px !important;font-size:16px !important;
    font-weight:500 !important;white-space:nowrap !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button p {
    font-size:16px !important;font-weight:inherit !important;white-space:nowrap !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:hover {
    background:#e8f1ff !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_"] button::before {
    content:"";display:inline-block;flex:0 0 23px;
    width:23px;height:23px;background-repeat:no-repeat;
    background-size:contain;background-position:center;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_dashboard"] button::before {background-image:url('ICON_DASH');}
section[data-testid="stSidebar"] div[class*="st-key-nav_register"] button::before {background-image:url('ICON_REG');}
section[data-testid="stSidebar"] div[class*="st-key-nav_list"] button::before {background-image:url('ICON_LIST');}
SELECTED_CSS
</style>
<div class="schedule-brand"><span class="schedule-brand-icon"><svg width="29" height="29" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="10" width="36" height="33" rx="6" fill="#EAF2FF"/><path d="M6 16 Q6 10 12 10 H36 Q42 10 42 16 V19 H6 Z" fill="#93C5FD"/><path d="M15 6 V14 M33 6 V14" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round"/><path d="M10 27 L24 21 L38 27 L24 33 Z" fill="#1D4ED8"/><path d="M17 30 V35 Q24 39 31 35 V30" fill="#60A5FA" stroke="#1D4ED8" stroke-width="1.5"/><path d="M38 27 V36" stroke="#1D4ED8" stroke-width="2"/></svg></span><span class="schedule-brand-name">학업 일정 관리 시스템</span></div>
<div class="schedule-menu-label">메뉴</div>
"""
_selected_css = """section[data-testid="stSidebar"] div[class*="st-key-nav_SELECTED"] button {
    background:#dceaff !important;color:#085ded !important;font-weight:800 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-nav_SELECTED"] button p {color:#085ded !important;font-weight:800 !important;}
"""
_active_key = {
    "대시보드":"dashboard", "일정 등록":"register",
    "일정 목록 (완료·수정·삭제)":"list"
}.get(st.session_state.active_schedule_menu,"dashboard")
_nav_css = (_nav_css.replace("ICON_DASH", "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23183358%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%20stroke-linecap%3D%22round%22%3E%3Cpath%20d%3D%22M3%2010%2012%203l9%207v10a1%201%200%200%201-1%201h-5v-7H9v7H4a1%201%200%200%201-1-1z%22%2F%3E%3C%2Fsvg%3E")
                   .replace("ICON_REG", "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23183358%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%20stroke-linecap%3D%22round%22%3E%3Ccircle%20cx%3D%2212%22%20cy%3D%2212%22%20r%3D%229%22%2F%3E%3Cpath%20d%3D%22M12%208v8M8%2012h8%22%2F%3E%3C%2Fsvg%3E")
                   .replace("ICON_LIST", "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23183358%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%20stroke-linecap%3D%22round%22%3E%3Cpath%20d%3D%22M9%206h12M9%2012h12M9%2018h12%22%2F%3E%3Ccircle%20cx%3D%224.5%22%20cy%3D%226%22%20r%3D%221%22%20fill%3D%22%23183358%22%2F%3E%3Ccircle%20cx%3D%224.5%22%20cy%3D%2212%22%20r%3D%221%22%20fill%3D%22%23183358%22%2F%3E%3Ccircle%20cx%3D%224.5%22%20cy%3D%2218%22%20r%3D%221%22%20fill%3D%22%23183358%22%2F%3E%3C%2Fsvg%3E")
                   .replace("SELECTED_CSS", _selected_css.replace("SELECTED",_active_key)))
st.sidebar.markdown(_nav_css, unsafe_allow_html=True)
st.sidebar.button("대시보드", key="nav_dashboard", width="stretch",
                  on_click=set_schedule_menu, args=("대시보드",))
st.sidebar.button("일정 등록", key="nav_register", width="stretch",
                  on_click=set_schedule_menu, args=("일정 등록",))
st.sidebar.button("일정 목록 (완료·수정·삭제)", key="nav_list", width="stretch",
                  on_click=set_schedule_menu, args=("일정 목록 (완료·수정·삭제)",))
st.sidebar.divider()
st.sidebar.caption(f"로그인 계정: {st.session_state.get('auth_email', '')}")
@st.fragment
def render_logout_button():
    if st.button("로그아웃", key="logout_button", width="stretch"):
        confirm_logout_dialog()

with st.sidebar:
    render_logout_button()

menu = st.session_state.active_schedule_menu

# 화면을 그리기 전에 필요한 일정 데이터를 먼저 조회
if menu in ("대시보드", "일정 목록 (완료·수정·삭제)"):
    schedules = load_schedules()

# ==================================================
# 일정 등록·대시보드 알림 디자인 통일
# 글씨 16px / 굵기 600 / 아이콘 22px / 최소 높이 46px
# ==================================================
if menu in ("대시보드", "일정 등록"):
    st.markdown(
        """
        <style>
        /* 알림박스 최소 높이 */
        div[data-testid="stAlert"],
        div[data-testid="stAlertContainer"] {
            min-height: 46px !important;
            box-sizing: border-box !important;
        }

        /* 알림 글씨 크기 및 굵기 */
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
            font-size: 16px !important;
            font-weight: 600 !important;
            line-height: 1.4 !important;
        }

        /* 알림 아이콘 크기 */
        div[data-testid="stAlert"] [data-testid="stAlertDynamicIcon"],
        div[data-testid="stAlert"] [data-testid="stIconMaterial"] {
            font-size: 22px !important;
            width: 22px !important;
            height: 22px !important;
            line-height: 22px !important;
            flex-shrink: 0 !important;
        }

        div[data-testid="stAlert"] [data-testid="stAlertDynamicIcon"] span {
            font-size: 22px !important;
            line-height: 22px !important;
        }

        div[data-testid="stAlert"] svg {
            width: 22px !important;
            height: 22px !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

# ==================================================
# 일정 등록 메뉴 진입 시 입력 상태 초기화
# ==================================================
if "previous_menu" not in st.session_state:
    st.session_state.previous_menu = menu

elif st.session_state.previous_menu != menu:

    # 일정 등록 메뉴에 새로 들어오는 경우
    if menu == "일정 등록":

        # 예상 소요시간을 1시간으로 초기화
        st.session_state.time_hours = 1
        st.session_state.hours_input = "1"
        st.session_state.hours_input_widget = "1"

        # 경고 상태 초기화
        st.session_state.hours_warning = None
        st.session_state.hours_input_invalid = False

    # 현재 메뉴 기록
    st.session_state.previous_menu = menu


# ==================================================
# 공통 제목
# ==================================================
if menu != "일정 목록 (완료·수정·삭제)":
    if menu == "일정 등록":
        st.markdown(
            '<div style="display:flex;align-items:center;gap:16px;'
            'margin-bottom:6px;">'
            '<span style="display:inline-flex;align-items:center;'
            'justify-content:center;width:58px;height:58px;'
            'background:#e8f0ff;border-radius:14px;flex-shrink:0;">'
            '<svg width="44" height="44" viewBox="0 0 64 64" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<path d="M5 23 30 12 55 23 30 35Z" fill="#1e40af"/>'
            '<path d="M17 30v9c0 6 6 10 13 10s13-4 13-10v-9" '
            'fill="#3b82f6" stroke="#1e40af" stroke-width="2"/>'
            '<path d="M55 23v12" stroke="#1e40af" '
            'stroke-width="2.5" stroke-linecap="round"/>'
            '<circle cx="49" cy="46" r="12" fill="#2563eb" '
            'stroke="#e8f0ff" stroke-width="3"/>'
            '<path d="M49 40v12M43 46h12" fill="none" '
            'stroke="#ffffff" stroke-width="3" '
            'stroke-linecap="round"/>'
            '</svg></span>'
            '<span style="font-size:clamp(26px,3vw,42px);'
            'font-weight:800;color:#2c3040;'
            'letter-spacing:-1px;line-height:1.2;">'
            '대학생 학업 일정 및 우선순위 관리 시스템'
            '</span></div>',
            unsafe_allow_html=True
        )
    else:
        st.title(
            "📅 대학생 학업 일정 및 우선순위 관리 시스템"
        )

    st.caption(
        "학업 일정을 관리하고 D-Day와 중요도, 예상 소요시간을 기반으로 "
        "우선순위를 자동 계산하는 프로그램입니다."
    )

    if menu == "일정 등록":
        st.markdown(
            '<div style="width:100%;height:1px;'
            'background:#d1d5db;margin:0;"></div>',
            unsafe_allow_html=True
        )
    else:
        st.divider()

# ==================================================
# 대시보드
# ==================================================
if menu == "대시보드":

    st.header(
        "대시보드"
    )

    # 완료한 일정은 추천 및 마감 알림 계산에서 제외
    pending_schedules = [
        schedule for schedule in schedules
        if not schedule["완료 여부"]
    ]

    # 오늘 마감인 미완료 일정
    today_tasks = [
        schedule for schedule in pending_schedules
        if schedule["D-Day"] == 0
    ]

    # 오늘부터 3일 이내 마감인 미완료 일정
    urgent_tasks = [
        schedule for schedule in pending_schedules
        if 0 <= schedule["D-Day"] <= 3
    ]

    # 기존 우선순위 정렬 결과 중 상위 3개 추천
    recommended_tasks = pending_schedules[:3]

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "오늘 마감 일정",
            f"{len(today_tasks)}개"
        )

    with col2:

        st.metric(
            "임박 일정",
            f"{len(urgent_tasks)}개"
        )

    with col3:

        st.metric(
            "전체 일정",
            f"{len(schedules)}개"
        )

    st.subheader("📌 오늘 할 일 추천")

    if recommended_tasks:
        for rank, schedule in enumerate(recommended_tasks, start=1):
            st.write(
                f"**{rank}순위 | "
                f"{schedule['과목명']} - {schedule['일정명']}** "
                f"| {format_dday(schedule['D-Day'])} "
                f"| 중요도: {schedule['중요도']} "
                f"| 우선순위: {schedule['우선순위 점수']}점"
            )
    else:
        info_notice("추천할 미완료 일정이 없습니다.")

    st.subheader(
        "⏰ 임박 일정"
    )

    if urgent_tasks:

        for schedule in urgent_tasks:

            st.write(
                f"{schedule['과목명']} - "
                f"{schedule['일정명']} "
                f"({format_dday(schedule['D-Day'])})"
            )

    else:

        info_notice(
            "3일 이내에 마감되는 일정이 없습니다."
        )


# ==================================================
# 일정 등록
# ==================================================
elif menu == "일정 등록":


    # ==============================================
    # 예상 소요시간 입력창 및 +/- 버튼 디자인
    # ==============================================
    st.markdown("""
        <style>

        /* 숫자 입력창 높이 */
        div[class*="st-key-hours_input"]
        div[data-baseweb="input"] {
            height: 40px !important;
            min-height: 40px !important;
        }

        /* 숫자 크기 및 굵기 */
        div[class*="st-key-hours_input"] input {
            height: 40px !important;
            font-size: 16px !important;
            font-weight: 400 !important;
        }

        /* +/- 버튼 높이 통일 */
        div[class*="st-key-hour_minus"] button,
        div[class*="st-key-hour_plus"] button {
            height: 40px !important;
            min-height: 40px !important;
            padding: 0 !important;
            border-radius: 6px !important;
        }

        /* +/- 기호 크기 */
        div[class*="st-key-hour_minus"] button p,
        div[class*="st-key-hour_plus"] button p {
            font-size: 24px !important;
            font-weight: bold !important;
            line-height: 1 !important;
            color: white !important;
        }

        /* 마이너스 버튼 - 빨간색 */
        div[class*="st-key-hour_minus"] button {
            background-color: #dc2626 !important;
            border-color: #dc2626 !important;
            color: white !important;
        }

        /* 플러스 버튼 - 파란색 */
        div[class*="st-key-hour_plus"] button {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            color: white !important;
        }

        /* 마이너스 버튼 마우스 올렸을 때 */
        div[class*="st-key-hour_minus"] button:hover {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
            color: white !important;
        }

        /* 플러스 버튼 마우스 올렸을 때 */
        div[class*="st-key-hour_plus"] button:hover {
            background-color: #1d4ed8 !important;
            border-color: #1d4ed8 !important;
            color: white !important;
        }

        </style>
    """, unsafe_allow_html=True)

    # ==================================================
    # 일정 등록 카드 디자인: 화면 구성만 변경
    # ==================================================
    st.markdown("""
    <style>
        div[class*="st-key-register_shell"] {
            background: #edf6ff !important;
            border-radius: 16px !important;
            padding: 12px !important;
            margin-top: -15px !important;
        }

        div[class*="st-key-register_card"] {
            background: #ffffff !important;
            border: 1px solid #dce6f5 !important;
            border-radius: 13px !important;
            padding: 14px 20px !important;
            box-shadow: 0 2px 7px rgba(30, 50, 80, .06) !important;
        }
        /* 경고·오류 알림은 기존 위치 보정을 유지한다. */
        div[class*="st-key-register_card"] [data-testid="stAlert"] {
            transform: translateY(-10px) !important;
        }
        div[class*="st-key-register_submit"] {
            width: 155px !important;
            max-width: 100% !important;
            margin-left: 0 !important;
            margin-right: auto !important;
            transform: none !important;
        }

        div[class*="st-key-register_submit"] button {
            width: 100% !important;
            height: 45px !important;
            min-height: 45px !important;
            border-radius: 8px !important;
            background: #2563eb !important;
            border: 1px solid #2563eb !important;
            color: white !important;
            padding: 0 12px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        div[class*="st-key-register_submit"] button:hover {
            background: #1d4ed8 !important;
            border-color: #1d4ed8 !important;
        }

        div[class*="st-key-register_submit"] button p {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 8px !important;
            margin: 0 !important;
            color: white !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            line-height: 1.2 !important;
            white-space: nowrap !important;
        }

        div[class*="st-key-register_submit"] button p::before {
            content: "✓";
            display: inline-block;
            font-size: 22px;
            font-weight: 400;
            line-height: 1;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)   

    with st.container(key="register_shell", gap=None):
        with st.container(key="register_card", border=True, gap="small"):
            st.markdown(
                '<div style="display:flex;align-items:center;gap:14px;'
                'padding:6px 0 4px;">'
                '<span style="display:flex;align-items:center;'
                'justify-content:center;width:48px;height:48px;'
                'border-radius:11px;background:#e8f0ff;'
                'flex-shrink:0;">'
                '<svg width="26" height="26" viewBox="0 0 24 24" '
                'fill="none" stroke="#2563eb" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M8 2v4M16 2v4M3 10h18"/>'
                '<path d="M4 4h16a2 2 0 0 1 2 2v5M4 4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10"/>'
                '<path d="M16 19h6M19 16v6"/>'
                '</svg></span>'
                '<div>'
                '<div style="font-size:27px;font-weight:800;'
                'color:#25314d;line-height:1.3;">일정 등록</div>'
                '<div style="font-size:14px;color:#667892;'
                'margin-top:5px;">'
                '새로운 학업 일정을 입력하고 등록합니다.'
                '</div>'
                '</div></div>',
                unsafe_allow_html=True
            )           

            st.divider()

            st.markdown(
                '<div style="display:flex;align-items:center;gap:9px;'
                'margin-top:-10px;padding:6px 0 14px;">'
                '<svg width="20" height="20" viewBox="0 0 24 24" '
                'fill="none" stroke="#2563eb" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M12 7v14"/>'
                '<path d="M3 18V5a1 1 0 0 1 1-1h3a5 5 0 0 1 5 5'
                ' 5 5 0 0 1 5-5h3a1 1 0 0 1 1 1v13'
                'a1 1 0 0 1-1 1h-4a4 4 0 0 0-4 2'
                ' 4 4 0 0 0-4-2H4a1 1 0 0 1-1-1Z"/>'
                '</svg>'
                '<span style="font-size:19px;font-weight:800;'
                'color:#203253;">기본 정보</span>'
                '</div>',
                unsafe_allow_html=True
            )            
            subject_col, schedule_col = st.columns(
                2, gap="medium", vertical_alignment="bottom", wrap=True
            )
            with subject_col:
                subject = st.text_input(
                    "과목명", placeholder="예: 캡스톤디자인"
                )
            with schedule_col:
                schedule_name = st.text_input(
                    "일정명", placeholder="예: 주간 개인 활동 리포트 제출"
                )

            st.divider()
            st.markdown(
                '<div style="display:flex;align-items:center;gap:9px;'
                'margin-top:-10px;padding:6px 0 18px;">'
                '<svg width="20" height="20" viewBox="0 0 24 24" '
                'fill="none" stroke="#2563eb" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round">'
                '<path d="M8 2v4M16 2v4M3 10h18"/>'
                '<path d="M21 12V6a2 2 0 0 0-2-2H5'
                'a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7"/>'
                '<circle cx="18" cy="18" r="4"/>'
                '<path d="M18 16v2l1.5 1"/>'
                '</svg>'
                '<span style="font-size:19px;font-weight:800;'
                'color:#203253;">일정 설정</span>'
                '</div>',
                unsafe_allow_html=True
            )
            deadline_col, importance_col = st.columns(
                2, gap="medium", vertical_alignment="bottom", wrap=True
            )
            with deadline_col:
                deadline = st.date_input("마감일", value=date.today())
            with importance_col:
                importance = st.selectbox(
                    "중요도", ["높음", "보통", "낮음"]
                )

            # 기존 예상 소요시간 처리 및 위젯 키 유지
            if "hours_input" not in st.session_state:
                st.session_state.hours_input = str(
                    st.session_state.time_hours
                )
            st.markdown(
                '<div style="display:flex;align-items:center;gap:4px;'
                'flex-wrap:wrap;">'
                '<span style="font-weight:700;font-size:16px;'
                'color:#263650;">예상 소요시간</span>'
                '<span style="font-size:13px;color:#64748b;">'
                '※ 1~100시간 입력 가능 (입력 후 Enter)'
                '</span></div>',
                unsafe_allow_html=True
            )

            input_col, minus_col, plus_col, gap_col, submit_col, empty_col = st.columns(
                [1.7, 0.55, 0.55, 0.65, 1.4, 2.35],
                gap="small", vertical_alignment="center", wrap=True
            )
            with input_col:
                if "hours_input_widget" not in st.session_state:
                    st.session_state.hours_input_widget = (
                        st.session_state.hours_input
                    )
                st.text_input(
                    "시간 입력",
                    key="hours_input_widget",
                    label_visibility="collapsed",
                    on_change=limit_hours_input
                )
            with minus_col:
                st.button(
                    "−", key="hour_minus", width="stretch",
                    on_click=change_hours, args=(-1,)
                )
            with plus_col:
                st.button(
                    "+", key="hour_plus", width="stretch",
                    on_click=change_hours, args=(1,)
                )
            # 일정 등록 버튼 방향 안내
            with gap_col:
                st.markdown(
                    '<div style="width:100%;height:45px;'
                    'display:flex;flex-direction:column;'
                    'align-items:center;justify-content:center;'
                    'gap:3px;transform:translateY(-15px);">'
                    '<span style="font-size:12px;font-weight:500;'
                    'color:#93B4E8;white-space:nowrap;'
                    'line-height:1;">등록하기</span>'
                    '<svg width="90%" height="16" '
                    'viewBox="0 0 90 16" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path d="M3 8 H85 M78 2 L85 8 L78 14" '
                    'fill="none" stroke="#93B4E8" '
                    'stroke-width="2" stroke-linecap="round" '
                    'stroke-linejoin="round"/>'
                    '</svg></div>',
                    unsafe_allow_html=True
                )

            # 예상 소요시간 안내 문구 오른쪽에 일정 등록 버튼
            with submit_col:
                with st.container(key="register_submit"):
                    register_clicked = st.button(
                        "일정 등록",
                        type="primary",
                        on_click=limit_hours_input,
                        width="stretch"
                    )

            current_hours = get_time_hours()
            st.session_state.time_hours = current_hours

            # 경고 또는 등록 결과가 있을 때만 하단 영역 표시
            footer_divider = st.empty()
            footer_notice = StyledAlertSlot()

            if st.session_state.get("hours_warning") or register_clicked:
                footer_divider.divider()

            if st.session_state.get("hours_warning"):
                footer_notice.warning(
                    st.session_state["hours_warning"]
                )                       

            # 이 아래의 등록 검증·DB 저장·점수 계산은 기존 코드 유지
            if register_clicked and not st.session_state.get(
                "hours_input_invalid", False
            ):
                current_hours = get_time_hours()

                expected_time = current_hours

                if not subject.strip():

                    footer_notice.warning(
                        "과목명을 입력해주세요."
                    )

                elif not schedule_name.strip():

                    footer_notice.warning(
                        "일정명을 입력해주세요."
                    )

                elif expected_time <= 0:

                    footer_notice.warning(
                        "예상 소요시간을 입력해주세요."
                    )

                # 중복 일정 등록 방지
                elif is_duplicate_schedule(
                    subject,
                    schedule_name,
                    deadline
                ):

                    footer_notice.warning(
                        f"{schedule_target(subject, schedule_name)} 일정이 이미 등록되어 있습니다. "
                        "동일한 과목명, 일정명, 마감일이 존재합니다."
                    )
                else:

                    # RLS가 보호하는 현재 사용자 일정으로 저장한다.
                    try:
                        inserted = (
                            db.table("schedules")
                            .insert({
                                "user_id": current_user_id,
                                "subject": subject.strip(),
                                "schedule_name": schedule_name.strip(),
                                "deadline": deadline.strftime("%Y-%m-%d"),
                                "importance": importance,
                                "expected_time": expected_time,
                            })
                            .select("id")
                            .execute()
                        )
                    except Exception:
                        footer_notice.error(
                            f"{schedule_target(subject, schedule_name)} "
                            "일정 등록에 실패했습니다. 다시 시도해주세요."
                        )
                        st.stop()
                    if not inserted.data:
                        footer_notice.error(
                            f"{schedule_target(subject, schedule_name)} "
                            "일정 등록에 실패했습니다. 다시 시도해주세요."
                        )
                        st.stop()

                    dday = (
                        deadline
                        - date.today()
                    ).days

                    priority = calculate_priority(
                        dday,
                        importance,
                        expected_time
                    )

                    # 등록 성공 알림: 단색 체크 아이콘 적용
                    footer_notice.success(
                        f"{schedule_target(subject, schedule_name)} "
                        "일정이 정상적으로 등록되었습니다."
                    )
# ==================================================
# 일정 목록: 최종 시안에 따른 UI 정렬·스크롤·검색
# ==================================================
elif menu == "일정 목록 (완료·수정·삭제)":
    st.markdown(r"""
    <style>
      /* 넓은 목록 레이아웃: 실제 브라우저 크기에 맞춤 */
      div[data-testid="stMainBlockContainer"] {
          max-width: 1450px !important;
          padding: 16px 20px 26px !important;
      }
      /* 검색 도구 */
      div[class*="st-key-schedule_filter_box"] {
          background:#f3f8ff !important;border:1px solid #dce6f5 !important;
          border-radius:12px !important;padding:13px 15px 10px !important;
      }
      div[class*="st-key-schedule_filter_box"] label p {
          color:#203253 !important;font-size:14px !important;font-weight:700 !important;
      }
      div[class*="st-key-schedule_keyword"] input {
          background-color:white !important;
          min-height:46px !important;height:46px !important;
          border:1px solid #cbd7ea !important;border-radius:8px !important;
          padding-left:45px !important;font-size:15px !important;
          background-image:url('DATA_SEARCH') !important;
          background-repeat:no-repeat !important;
          background-size:22px 22px !important;
          background-position:15px center !important;
      }
      div[class*="st-key-schedule_subject_filter"] div[data-baseweb="select"] > div {
          height:46px !important;min-height:46px !important;
          background:white !important;border:1px solid #cbd7ea !important;
          border-radius:8px !important;font-size:15px !important;
      }
      div[class*="st-key-reset_schedule_search"] button {
          height:46px !important;min-height:46px !important;
          border:1px solid #2563eb !important;border-radius:8px !important;
          background:white !important;color:#075fec !important;
          font-size:15px !important;font-weight:700 !important;
          white-space:nowrap !important;
      }
      div[class*="st-key-reset_schedule_search"] button:hover {
          background:#e9f2ff !important;
      }
      /* 미완료·완료 구획 */
      div[class*="st-key-schedule_panel_"] {
          padding:9px !important;border:1px solid #dce5f1 !important;
          border-radius:13px !important;
          box-shadow:0 2px 7px rgba(30,50,80,.07) !important;
      }
      div[class*="st-key-schedule_panel_open"] {background:#edf6ff !important;}
      div[class*="st-key-schedule_panel_done"] {background:#eefaF5 !important;}

      /* 미완료 영역 */
      div[class*="st-key-schedule_slot_open"] {
          min-height:510px !important;
          height:auto !important;
          box-sizing:border-box !important;
          overflow:visible !important;
      }

      /* 완료 영역 */
      div[class*="st-key-schedule_slot_done"] {
          min-height:530px !important;
          height:auto !important;
          box-sizing:border-box !important;
          overflow:visible !important;
      }
      div[class*="st-key-schedule_table_"] {
          background:#fff !important;border:1px solid #e0e6f0 !important;
          border-radius:10px !important;
          padding:4px 6px 4px !important;
      }
      div[class*="st-key-schedule_table_"] div[data-testid="stVerticalBlock"],
      div[class*="st-key-schedule_scroll_"] div[data-testid="stVerticalBlock"] {
          gap:0 !important;
      }
      /* 헤더는 스크롤 영역 밖에 배치해 스크롤해도 고정 */
      div[class*="st-key-schedule_heading_"] {
          background:#f3f6fa !important;
          border-radius:7px !important;
          border-bottom:1px solid #e1e8f1 !important;
      }

      /* 스크롤바가 있는 목록의 헤더 너비 보정 */
      div[class*="st-key-schedule_heading_open_scroll"],
      div[class*="st-key-schedule_heading_done_scroll"] {
          padding-right:12px !important;
          box-sizing:border-box !important;
      }
      div[class*="st-key-schedule_heading_"] [data-testid="stHorizontalBlock"] {
          min-height:35px !important;
          align-items:center !important;
      }

      /* 표 헤더 글자 위치 보정 */
      div[class*="st-key-schedule_heading_"] [data-testid="stMarkdown"] {
          transform:translateY(-5px) !important;
      }
      
      /* 표 헤더와 개별 일정 행에는 독립 스크롤을 만들지 않음 */
      div[class*="st-key-schedule_heading_"] [data-testid="stHorizontalBlock"],
      div[class*="st-key-schedule_row_"] [data-testid="stHorizontalBlock"] {
          overflow-x:visible !important;
          overflow-y:visible !important;
      }

      div[class*="st-key-schedule_heading_"] [data-testid="stColumn"],
      div[class*="st-key-schedule_row_"] [data-testid="stColumn"] {
          min-width:0 !important;
      }

      /* 일정 행 기본 높이 및 구분선 */
      div[class*="st-key-schedule_row_"] {
          border-bottom:1px solid #e2e8f1 !important;
          min-height:46px !important;
          padding:0 !important;
      }

      /* 일정 행 가로 배치 및 세로 중앙 정렬 */
      div[class*="st-key-schedule_row_"] [data-testid="stHorizontalBlock"] {
          min-height:46px !important;
          align-items:center !important;
      }

      /* 텍스트 기본 여백 제거 */
      div[class*="st-key-schedule_row_"] [data-testid="stMarkdownContainer"] p {
          margin:0 !important;
      }

      /* 일정 행 내부 간격 제거 */
      div[class*="st-key-schedule_row_"] div[data-testid="stVerticalBlock"] {
          gap:0 !important;
      }

      /* 일정 데이터의 세로 위치 보정 */
      div[class*="st-key-schedule_row_"] [data-testid="stMarkdown"] {
          transform: translateY(-8px) !important;
      }

      /* 스크롤은 schedule_scroll 컨테이너에서만 담당 */
      /* 미완료·완료 일정 스크롤바 크기 */
      div[class*="st-key-schedule_scroll_"] {
          scrollbar-width:auto !important;
          scrollbar-color:#9aa0a6 #f4f6f9 !important;
      }

      div[class*="st-key-schedule_scroll_"]::-webkit-scrollbar,
      div[class*="st-key-schedule_scroll_"] *::-webkit-scrollbar {
          width:12px !important;
      }

      /* 스크롤바 배경 */
      div[class*="st-key-schedule_scroll_"]::-webkit-scrollbar-track,
      div[class*="st-key-schedule_scroll_"] *::-webkit-scrollbar-track {
          background:#f4f6f9 !important;
          border-radius:10px !important;
      }

      /* 스크롤바 움직이는 부분 */
      div[class*="st-key-schedule_scroll_"]::-webkit-scrollbar-thumb,
      div[class*="st-key-schedule_scroll_"] *::-webkit-scrollbar-thumb {
          background:#9aa0a6 !important;
          border-radius:10px !important;
          border:1px solid #f4f6f9 !important;
      }
       /* 관리 버튼 공통 크기 */
      div[class*="st-key-mark_done_"] button,
      div[class*="st-key-edit_"] button,
      div[class*="st-key-delete_"] button,
      div[class*="st-key-undo_done_"] button {
          width:100% !important;
          max-width:100% !important;
          height:34px !important;
          min-height:34px !important;
          padding:0 3px !important;
          margin:0 !important;
          border-radius:6px !important;
          font-size:13px !important;
          font-weight:700 !important;
          white-space:nowrap !important;
      }
      /* 미완료·완료 일정 관리 버튼 그룹 중앙 정렬 */
      div[class*="st-key-schedule_row_"]
      [data-testid="stHorizontalBlock"]:has(
          > [data-testid="stColumn"]:first-child
          [class*="st-key-mark_done_"]
      ),
      div[class*="st-key-schedule_row_"]
      [data-testid="stHorizontalBlock"]:has(
          > [data-testid="stColumn"]:first-child
          [class*="st-key-undo_done_"]
      ) {
          display:flex !important;
          width:100% !important;
          gap:8px !important;
          justify-content:center !important;
          align-items:center !important;
          padding:0 !important;
          margin:0 auto !important;
          box-sizing:border-box !important;
      }
     
      div[class*="st-key-schedule_row_"]
      [data-testid="stHorizontalBlock"]:has(
          > [data-testid="stColumn"]:first-child
          [class*="st-key-mark_done_"]
      ) > [data-testid="stColumn"] {
          flex:0 0 72px !important;
          width:72px !important;
          max-width:72px !important;
          min-width:0 !important;
      }

      div[class*="st-key-schedule_row_"]
      [data-testid="stHorizontalBlock"]:has(
          > [data-testid="stColumn"]:first-child
          [class*="st-key-undo_done_"]
      ) > [data-testid="stColumn"] {
          flex:0 0 100px !important;
          width:100px !important;
          max-width:100px !important;
          min-width:0 !important;
      }    

      div[class*="st-key-mark_done_"] button {background:#078c43 !important;border:1px solid #078c43 !important;color:white !important;}
      div[class*="st-key-mark_done_"] button:hover {background:#067439 !important;border-color:#067439 !important;}
      div[class*="st-key-edit_"] button {background:#2563eb !important;border:1px solid #2563eb !important;color:white !important;}
      div[class*="st-key-edit_"] button:hover {background:#1d4ed8 !important;border-color:#1d4ed8 !important;}
      div[class*="st-key-delete_"] button {background:#df2030 !important;border:1px solid #df2030 !important;color:white !important;}
      div[class*="st-key-delete_"] button:hover {background:#bf1d29 !important;border-color:#bf1d29 !important;}
      div[class*="st-key-undo_done_"] button {background:white !important;border:1px solid #119348 !important;color:#087e3f !important;}
      div[class*="st-key-undo_done_"] button:hover {background:#dcfce7 !important;border-color:#087e3f !important;}
    </style>
    """.replace('DATA_SEARCH','data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23183358%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%20stroke-linecap%3D%22round%22%3E%3Ccircle%20cx%3D%2210.5%22%20cy%3D%2210.5%22%20r%3D%227%22%2F%3E%3Cpath%20d%3D%22m16%2016%205%205%22%2F%3E%3C%2Fsvg%3E'), unsafe_allow_html=True)

    # ==============================================
    # 일정 목록 제목 오른쪽에 실제 일정명과 기능별 알림 표시
    # ==============================================
    action_message = st.session_state.pop("action_message", None)
    action_error = st.session_state.pop("action_error", None)
    if action_message and action_message.get("kind") in ("edit", "delete", "complete", "undo"):
        notice_content = action_notice_html(
            action_message["kind"],
            action_message.get("subject", ""),
            action_message.get("schedule_name", ""),
            size="header",
        )
    elif action_error:
        notice_content = notice_html("error", action_error, size="header")
    else:
        notice_content = ""

    st.markdown(
        '<div style="display:flex;'
        'align-items:center;'
        'justify-content:flex-start;'
        'flex-wrap:wrap;'
        'gap:0px;'
        'min-height:70px;'
        'width:100%;'
        'box-sizing:border-box;">'

        '<div style="display:flex;'
        'align-items:center;'
        'gap:14px;'
        'min-height:48px;">'

        '<span style="display:inline-flex;'
        'align-items:center;'
        'justify-content:center;'
        'width:48px;'
        'height:48px;'
        'flex-shrink:0;'
        'background:#e8f0ff;'
        'border-radius:11px;">'

        '<svg width="28" height="28" viewBox="0 0 24 24" '
        'xmlns="http://www.w3.org/2000/svg" '
        'fill="none" stroke="#2563eb" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M13 5h8M13 13h8M13 21h8"/>'
        '<path d="m3 5 2 2 4-4M3 13l2 2 4-4M3 21l2 2 4-4"/>'
        '</svg>'
        '</span>'

        '<h2 style="margin:0;'
        'font-size:32px;'
        'font-weight:700;'
        'line-height:1.2;'
        'color:#25314d;'
        'display:flex;'
        'align-items:center;'
        'min-height:48px;'
        'transform:translateY(2px);">'
        '일정 목록 (완료·수정·삭제)'
        '</h2>'

        '</div>'

        f'{notice_content}'
        '</div>',
        unsafe_allow_html=True
    )

    # 일정 목록 설명
    st.markdown(
        '<div style="font-size:17px;color:#405577;margin-top:-4px;'
        'margin-bottom:14px;">'
        '등록된 학업 일정을 우선순위 순서로 확인하고 관리합니다.'
        '</div>',
        unsafe_allow_html=True
    )

    def change_completion_status(schedule_id, make_done, subject_name, schedule_name):
        kind = "complete" if make_done else "undo"
        try:
            changed = (
                complete_schedule(schedule_id)
                if make_done else cancel_schedule_completion(schedule_id)
            )
        except Exception:
            changed = False

        if changed:
            st.session_state["action_message"] = {
                "kind": kind, "subject": subject_name, "schedule_name": schedule_name
            }
            st.session_state.pop("action_error", None)
        else:
            st.session_state["action_message"] = None
            operation = "완료 처리" if make_done else "완료 취소"
            st.session_state["action_error"] = (
                f"{schedule_target(subject_name, schedule_name)} "
                f"일정 {operation}에 실패했습니다. 다시 시도해주세요."
            )

    subjects = sorted({s["과목명"] for s in schedules})
    subject_options = ["전체 과목"] + subjects
    if st.session_state.get("schedule_subject_filter", "전체 과목") not in subject_options:
        st.session_state["schedule_subject_filter"] = "전체 과목"

    def reset_schedule_search():
        st.session_state["schedule_keyword"] = ""
        st.session_state["schedule_subject_filter"] = "전체 과목"

    with st.container(key="schedule_filter_box", gap="xxsmall"):
        search_col, subject_col, reset_col = st.columns(
            [5.7, 3.1, 1.65], gap="medium", vertical_alignment="bottom"
        )
        with search_col:
            st.text_input(
                "과목명 또는 일정명 검색",
                key="schedule_keyword",
                placeholder="과목명 또는 일정명을 입력하세요..."
            )
        with subject_col:
            st.selectbox("과목 선택", subject_options, key="schedule_subject_filter")
        with reset_col:
            st.button(
                "⟳  검색 초기화",key="reset_schedule_search", width="stretch",
                on_click=reset_schedule_search
            )

    keyword = st.session_state.get("schedule_keyword", "").strip().casefold()
    subject = st.session_state.get("schedule_subject_filter", "전체 과목")
    filtered = [
        s for s in schedules
        if (not keyword or keyword in s["과목명"].casefold() or keyword in s["일정명"].casefold())
        and (subject == "전체 과목" or s["과목명"] == subject)
    ]
    if (keyword or subject != "전체 과목") and not filtered:
        info_notice("검색 조건에 일치하는 일정이 없습니다.")

    pending = [s for s in filtered if not s["완료 여부"]]
    completed = sorted(
        [s for s in filtered if s["완료 여부"]],
        key=lambda s: (s["완료 일시"] or "", s["id"]), reverse=True
    )

    # 헤더와 데이터가 완전히 같은 9개 열 비율로 배치됨
    grid_widths = [0.69, 1.12, 2.02, 1.12, 0.78, 0.85, 1.08, 1.10, 2.10]
    grid_headers = [
        "순위", "과목명", "일정명", "마감일", "D-Day", "중요도",
        "예상 소요시간", "우선순위(점수)", "관리"
    ]

    def regular_cell(value, bold=False, color="#263650", fontsize=14):
        st.markdown(
            '<div style="min-height:45px;display:flex;align-items:center;'
            'justify-content:center;text-align:center;padding:0 3px;'
            'border-right:1px solid #e2e8ef;overflow-wrap:anywhere;'
            f'font-size:{fontsize}px;font-weight:{700 if bold else 400};'
            f'color:{color};line-height:1.25;">{escape(str(value))}</div>',
            unsafe_allow_html=True
        )

    def badge_cell(value, bg, color, fontsize=14):
        st.markdown(
            '<div style="min-height:45px;display:flex;align-items:center;'
            'justify-content:center;border-right:1px solid #e2e8ef;">'
            f'<span style="display:inline-block;padding:5px 10px;'
            f'border-radius:7px;background:{bg};color:{color};'
            f'font-size:{fontsize}px;font-weight:700;line-height:1.35;">'
            f'{escape(str(value))}</span></div>',
            unsafe_allow_html=True
        )

    def draw_table_rows(entries, section_completed):
        if not entries:
            if section_completed:
                message = "완료한 일정이 없습니다."
            elif not schedules:
                message = "등록된 학업 일정이 없습니다."
            else:
                message = "미완료 일정이 없습니다."
            info_notice(message)
            return
        for n, item in enumerate(entries,1):
            sid = item["id"]
            remaining = item["D-Day"]
            dday_color = "#2563eb" if remaining < 0 else "#dc2626" if remaining <= 3 else "#2d405f"
            with st.container(key=f"schedule_row_{sid}", gap=None):
                # 각 행에서 별도 스크롤바를 만드는 no-wrap 배치를 사용하지 않는다.
                cols = st.columns(grid_widths, gap="xxsmall", vertical_alignment="center", wrap=True)
                with cols[0]:
                    if section_completed:
                        completed_raw = item.get("완료 일시")

                        try:
                            completed_date = datetime.fromisoformat(
                                str(completed_raw)
                            ).date()

                            completed_label = (
                                f"{completed_date.month}/{completed_date.day}"
                            )

                        except (ValueError, TypeError):
                            completed_label = "—"

                        badge_cell(
                            completed_label,
                            "#edf0f4",
                            "#536176",
                            fontsize=14
                        )

                    else:
                        badge_cell(
                            f"{n}위",
                            "#fee2e2",
                            "#e0242e",
                            fontsize=14
                        )
                with cols[1]:
                    regular_cell(item["과목명"], fontsize=14)
                with cols[2]:
                    regular_cell(item["일정명"], bold=True, fontsize=15)
                with cols[3]:
                    regular_cell(item["마감일"], fontsize=14)
                with cols[4]:
                    regular_cell(format_dday(remaining), bold=True,color=dday_color,fontsize=14)
                with cols[5]:
                    importance_colors={"높음":("#fee2e2","#dc2626"),"보통":("#dceafb","#2563eb"),"낮음":("#dcfce7","#15803d")}
                    bg, fg = importance_colors.get(item["중요도"],("#f1f5f9","#334155"))
                    badge_cell(item["중요도"],bg,fg)
                with cols[6]:
                    regular_cell(format_expected_time(item["예상 소요시간"]),fontsize=14)
                with cols[7]:
                    regular_cell(item["우선순위 점수"],fontsize=14)
                with cols[8]:
                    if section_completed:
                        # 같은 폭의 두 버튼, 완료된 일정에서는 수정 없음
                        col_undo,col_delete=st.columns([1,1],gap="xsmall",vertical_alignment="center")
                        with col_undo:
                            st.button("완료 취소",key=f"undo_done_{sid}",width="stretch",
                                      on_click=change_completion_status,args=(sid,False,item["과목명"],item["일정명"]))
                        with col_delete:
                            if st.button("삭제",key=f"delete_{sid}",width="stretch"):
                                delete_schedule_dialog(item)
                    else:
                        col_done,col_edit,col_delete=st.columns([1,1,1],gap="xsmall",vertical_alignment="center")
                        with col_done:
                            st.button("완료",key=f"mark_done_{sid}",width="stretch",
                                      on_click=change_completion_status,args=(sid,True,item["과목명"],item["일정명"]))
                        with col_edit:
                            if st.button(
                                "수정",
                                key=f"edit_{sid}",
                                width="stretch"
                            ):
                                # DB에 저장된 예상 소요시간으로 초기화
                                st.session_state[f"edit_hours_input_{sid}"] = str(
                                    int(item["예상 소요시간"])
                                )

                                # 이전 경고 상태 초기화
                                st.session_state[f"edit_hours_warning_{sid}"] = None
                                st.session_state[f"edit_hours_invalid_{sid}"] = False

                                edit_schedule_dialog(item)
                        with col_delete:
                            if st.button("삭제",key=f"delete_{sid}",width="stretch"):
                                delete_schedule_dialog(item)

    def draw_section(entries, section_completed, scroll_height):
        key = "done" if section_completed else "open"
        panel_bg = "#effaf5" if section_completed else "#edf6ff"
        title_color = "#077e3e" if section_completed else "#075cec"
        title = "완료 일정" if section_completed else "미완료 일정"
        description = (
            "완료한 일정을 확인하고 필요시 완료 상태를 취소하거나 삭제할 수 있습니다."
            if section_completed else "완료되지 않은 일정을 우선순위 순서로 확인하고 관리합니다."
        )
        order = "완료일 최신순" if section_completed else "우선순위 높은 순"
        glyph = "✓" if section_completed else "▦"
        glyph_bg = "#08934c" if section_completed else "#2563eb"
        with st.container(key=f"schedule_panel_{key}", border=True, gap="xsmall"):
            st.markdown(
                '<div style="display:flex;align-items:center;justify-content:space-between;'
                'min-height:62px;padding:3px 5px 7px;gap:9px;">'
                '<div style="display:flex;align-items:center;gap:13px;">'
                f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'width:36px;height:36px;border-radius:7px;background:{glyph_bg};'
                f'color:#fff;font-size:24px;font-weight:700;">{glyph}</span>'
                f'<div><div style="font-size:21px;font-weight:800;color:{title_color};'
                f'line-height:29px;">{title} ({len(entries)})</div>'
                f'<div style="font-size:14px;color:#405b7d;line-height:21px;">{description}</div></div></div>'
                f'<span style="font-size:14px;color:#203653;white-space:nowrap;">{order}</span>'
                '</div>', unsafe_allow_html=True
            )
            with st.container(key=f"schedule_table_{key}", border=True, gap=None):
                # 헤더는 별도 영역: 일정 행을 스크롤해도 제목은 움직이지 않음.
                with st.container(
                    key=f"schedule_heading_{key}{'_scroll' if len(entries) > 6 else ''}",
                    gap=None
                ):
                    header_cols = st.columns(
                        grid_widths, gap="xxsmall",
                        vertical_alignment="center", wrap=True
                    )
                    for col, header_name in zip(header_cols, grid_headers):
                        with col:
                            display_name = (
                                "완료일"
                                if section_completed and header_name == "순위"
                                else header_name
                            )

                            st.markdown(
                                f'<div style="height:35px;display:flex;align-items:center;'
                                f'justify-content:center;text-align:center;font-size:14px;'
                                f'font-weight:700;color:#1e304c;line-height:1.1;'
                                f'white-space:nowrap;">{escape(display_name)}</div>',
                                unsafe_allow_html=True
                            )

                # 표 헤더는 스크롤 밖에 고정하고 일정 데이터만 하나의 영역에서 스크롤.
                # 개수 제한/페이지 분할 없이 모든 일정을 렌더링한다.
                # 일정이 적으면 빈 공간이 생기지 않도록 높이를 자동 축소하고,
                # 많으면 최대 높이를 유지한 채 해당 영역에서 끝까지 스크롤한다.
                # 적은 일정은 실제 내용만큼만 표시해 불필요한 세로 스크롤을 막는다.
                # 일정이 많으면 세로 스크롤을 1개만 만들고 모든 행을 렌더링한다.
                if len(entries) <= 6:
                    row_view_height = "content"
                elif len(entries) == 7:
                    row_view_height = 330
                else:
                    row_view_height = scroll_height

                with st.container(
                    key=f"schedule_scroll_{key}",
                    border=False,
                    height=row_view_height,
                    gap=None,
                    autoscroll=False
                ):
                    draw_table_rows(entries, section_completed)

    # ==============================================
    # 미완료 일정: 독립된 배치 공간
    # ==============================================
    with st.container(
        key="schedule_slot_open",
        gap=None
    ):
        draw_section(pending, False, 365)

    # ==============================================
    # 미완료·완료 일정 사이 구분선 중앙 정렬
    # ==============================================
    st.markdown(
        '<div style="height:1px;'
        'background:#dce4ef;'
        'margin:10px 0;'
        'border-radius:2px;'
        'transform:translateY(-20px);"></div>',
        unsafe_allow_html=True
    )

    # ==============================================
    # 완료 일정: 독립된 배치 공간
    # ==============================================
    with st.container(
        key="schedule_slot_done",
        gap=None
    ):
        draw_section(completed, True, 365)

# Supabase는 요청마다 인증된 클라이언트가 관리하므로 SQLite 연결 종료가 필요 없다.