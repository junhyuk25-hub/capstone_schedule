import sqlite3
from datetime import date, datetime
from pathlib import Path
from html import escape

import streamlit as st

# ==================================================
# 기본 설정
# ==================================================
st.set_page_config(
    page_title="학업 일정 관리 시스템",
    page_icon="📅",
    layout="wide"
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
# 데이터베이스 연결
# ==================================================

# app.py가 있는 폴더의 schedule.db 사용
DB_PATH = Path(__file__).resolve().parent / "schedule.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    deadline TEXT NOT NULL,
    importance TEXT NOT NULL,
    expected_time REAL NOT NULL
)
""")

conn.commit()


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
# 일정 불러오기
# ==================================================
def load_schedules():

    cursor.execute("""
        SELECT
            id,
            subject,
            schedule_name,
            deadline,
            importance,
            expected_time
        FROM schedules
    """)

    rows = cursor.fetchall()

    schedules = []

    for row in rows:

        dday = calculate_dday(
            row[3]
        )

        priority = calculate_priority(
            dday,
            row[4],
            row[5]
        )

        schedules.append({
            "id": row[0],
            "과목명": row[1],
            "일정명": row[2],
            "마감일": row[3],
            "중요도": row[4],
            "예상 소요시간": row[5],
            "D-Day": dday,
            "우선순위 점수": priority
        })

    schedules.sort(
        key=lambda x: (
            -x["우선순위 점수"],
            x["D-Day"],
            x["id"]
        )
    )

    return schedules

# ==================================================
# 중복 일정 검사 (띄어쓰기 정리 포함)
# ==================================================
def is_duplicate_schedule(
    subject,
    schedule_name,
    deadline,
    exclude_id=None
):

    # 앞뒤 공백 제거 및 중간 공백 하나로 통일
    normalized_subject = " ".join(subject.split())
    normalized_name = " ".join(schedule_name.split())

    deadline_text = deadline.strftime("%Y-%m-%d")

    # 동일한 마감일의 일정 조회
    with sqlite3.connect(DB_PATH) as check_conn:

        rows = check_conn.execute("""
            SELECT id, subject, schedule_name
            FROM schedules
            WHERE deadline = ?
        """, (deadline_text,)).fetchall()

    # 기존 일정들과 비교
    for row_id, saved_subject, saved_name in rows:

        # 수정 중인 자기 자신은 제외
        if exclude_id is not None and row_id == exclude_id:
            continue

        # 기존 일정의 띄어쓰기도 동일하게 정리
        saved_subject = " ".join(saved_subject.split())
        saved_name = " ".join(saved_name.split())

        # 과목명과 일정명이 모두 같으면 중복
        if (
            normalized_subject == saved_subject
            and normalized_name == saved_name
        ):
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

    # 0시간에서 - 버튼 클릭
    elif amount < 0 and hours <= 0:

        st.session_state.hours_warning = (
            "예상 소요시간은 0시간 미만으로 설정할 수 없습니다. "
            "0시간으로 유지했습니다."
        )

    # 정상 범위
    else:

        hours = max(0, min(100, hours + amount))

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

    # 0시간 미만 입력
    if hours < 0:

        st.session_state.hours_input_invalid = True

        st.session_state.hours_warning = (
            "예상 소요시간은 0시간 미만으로 입력할 수 없습니다. "
            "시간을 다시 입력해주세요."
        )

        return

    # 정상적인 입력
    st.session_state.hours_input_invalid = False
    st.session_state.hours_warning = None

    st.session_state.hours_input = str(hours)
    st.session_state.time_hours = hours

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

    edit_expected_time = st.number_input(
        "예상 소요시간",
        min_value=1,
        max_value=100,
        value=max(
            1,
            int(selected_schedule["예상 소요시간"])
        ),
        step=1,
        format="%d"
    )

    st.write(
        f"현재 D-Day: "
        f"{format_dday(selected_schedule['D-Day'])}"
    )

    st.write(
        f"현재 우선순위 점수: "
        f"{selected_schedule['우선순위 점수']}"
    )

    if st.button("일정 수정", type="primary"):

        if not edit_subject.strip():
            st.warning("과목명을 입력해주세요.")

        elif not edit_schedule_name.strip():
            st.warning("일정명을 입력해주세요.")

        elif (
            edit_subject.strip() == selected_schedule["과목명"]
            and edit_schedule_name.strip() == selected_schedule["일정명"]
            and edit_deadline.strftime("%Y-%m-%d") == selected_schedule["마감일"]
            and edit_importance == selected_schedule["중요도"]
            and int(edit_expected_time) == int(selected_schedule["예상 소요시간"])
        ):
            st.warning(
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

            st.warning(
                "이미 등록된 일정입니다. "
                "동일한 과목명, 일정명, 마감일의 일정이 존재합니다. "
                "내용을 확인해주세요."
            )
        else:
            with sqlite3.connect(DB_PATH) as edit_conn:
                edit_conn.execute("""
                    UPDATE schedules
                    SET subject = ?,
                        schedule_name = ?,
                        deadline = ?,
                        importance = ?,
                        expected_time = ?
                    WHERE id = ?
                """, (
                    edit_subject.strip(),
                    edit_schedule_name.strip(),
                    edit_deadline.strftime("%Y-%m-%d"),
                    edit_importance,
                    edit_expected_time,
                    selected_schedule["id"]
                ))

            new_dday = (
                edit_deadline - date.today()
            ).days

            new_priority = calculate_priority(
                new_dday,
                edit_importance,
                edit_expected_time
            )

            st.session_state["action_message"] = {
                "kind": "edit",
                "dday": new_dday,
                "priority": new_priority
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

    st.warning("삭제한 일정은 복구할 수 없습니다.")

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

            with sqlite3.connect(DB_PATH) as delete_conn:
                delete_conn.execute("""
                    DELETE FROM schedules
                    WHERE id = ?
                """, (selected_schedule["id"],))

            st.session_state["action_message"] = {
                "kind": "delete"
            }

            st.rerun()

# ==================================================
# 사이드바
# ==================================================
st.sidebar.title(
    "📚 메뉴"
)

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "대시보드",
        "일정 등록",
        "일정 목록 (수정·삭제)",
    ]
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
st.title(
    "📅 대학생 학업 일정 및 우선순위 관리 시스템"
)

st.caption(
    "학업 일정을 관리하고 D-Day와 중요도, 예상 소요시간을 기반으로 "
    "우선순위를 자동 계산하는 프로그램입니다."
)

st.divider()


# ==================================================
# 대시보드
# ==================================================
if menu == "대시보드":

    st.header(
        "대시보드"
    )

    schedules = load_schedules()

    today_tasks = [
        schedule
        for schedule in schedules
        if schedule["D-Day"] == 0
    ]

    urgent_tasks = [
        schedule
        for schedule in schedules
        if 0 <= schedule["D-Day"] <= 3
    ]

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

    st.subheader(
        "🔥 우선순위 높은 일정"
    )

    if schedules:

        for index, schedule in enumerate(
            schedules[:5],
            start=1
        ):

            dday_text = format_dday(
                schedule["D-Day"]
            )

            st.write(
                f"**{index}순위 | "
                f"{schedule['과목명']} - "
                f"{schedule['일정명']}** "
                f"| {dday_text} "
                f"| 중요도: "
                f"{schedule['중요도']}"
            )

    else:

        st.info(
            "등록된 일정이 없습니다."
        )

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

        st.info(
            "3일 이내에 마감되는 일정이 없습니다."
        )


# ==================================================
# 일정 등록
# ==================================================
elif menu == "일정 등록":

    st.header(
        "일정 등록"
    )

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

    st.write(
        "새로운 학업 일정을 입력합니다."
    )

    subject = st.text_input(
        "과목명",
        placeholder="예: 캡스톤디자인"
    )

    schedule_name = st.text_input(
        "일정명",
        placeholder="예: 주간 개인 활동 리포트 제출"
    )

    deadline = st.date_input(
        "마감일",
        value=date.today()
    )

    importance = st.selectbox(
        "중요도",
        [
            "높음",
            "보통",
            "낮음"
        ]
    )

    # 중요도와 예상 소요시간 사이 여백
    st.write("")

    # ==============================================
    # 예상 소요시간
    # ==============================================

    if "hours_input" not in st.session_state:

        st.session_state.hours_input = str(
            st.session_state.time_hours
        )

    st.write(
        "예상 소요시간"
    )
    
    input_col, minus_col, plus_col, empty_col = st.columns(
        [2.3, 0.65, 0.65, 4.4],
        gap="small",
        vertical_alignment="center"
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
            "−",
            key="hour_minus",
            width="stretch",
            on_click=change_hours,
            args=(-1,)
        )

    with plus_col:

        st.button(
            "+",
            key="hour_plus",
            width="stretch",
            on_click=change_hours,
            args=(1,)
        )
    with empty_col:

        st.caption(
            "※ 1~100시간 입력 가능 (입력 후 Enter)"
        )

    # ==============================================
    # 예상 소요시간 경고창 표시
    # ==============================================
    if st.session_state.get("hours_warning"):

        warning_col, empty_warning_col = st.columns(
            [3.6, 4.4],
            gap="small"
        )

        with warning_col:

            st.warning(
                st.session_state["hours_warning"]
            )

    current_hours = get_time_hours()

    st.session_state.time_hours = current_hours

    # ==============================================
    # 일정 등록 버튼
    # ==============================================
    if st.button(
        "일정 등록",
        type="primary",
        on_click=limit_hours_input
    ) and not st.session_state.get("hours_input_invalid", False):

        current_hours = get_time_hours()

        expected_time = current_hours

        if not subject.strip():

            st.warning(
                "과목명을 입력해주세요."
            )

        elif not schedule_name.strip():

            st.warning(
                "일정명을 입력해주세요."
            )

        elif expected_time <= 0:

            st.warning(
                "예상 소요시간을 입력해주세요."
            )
        # 중복 일정 등록 방지
        elif is_duplicate_schedule(
            subject,
            schedule_name,
            deadline
        ):

            st.warning(
                "이미 등록된 일정입니다. "
                "동일한 과목명, 일정명, 마감일의 일정이 존재합니다. "
                "내용을 확인해주세요."
            )
        else:

            cursor.execute("""
                INSERT INTO schedules (
                    subject,
                    schedule_name,
                    deadline,
                    importance,
                    expected_time
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                subject.strip(),
                schedule_name.strip(),
                deadline.strftime(
                    "%Y-%m-%d"
                ),
                importance,
                expected_time
            ))

            conn.commit()

            dday = (
                deadline
                - date.today()
            ).days

            priority = calculate_priority(
                dday,
                importance,
                expected_time
            )

            st.success(
                "일정이 정상적으로 등록되었습니다."
            )

            st.info(
                f"D-Day: "
                f"{format_dday(dday)} | "
                f"자동 우선순위 점수: "
                f"{priority}"
            )


# ==================================================
# 일정 목록
# ==================================================
elif menu == "일정 목록 (수정·삭제)":

    st.header("일정 목록")
    # ==================================================
    # 일정 목록 디자인
    # ==================================================
    st.markdown("""
        <style>

        /* 표 제목과 내용 가운데 정렬 */
        div[data-testid="stMain"]
        div[data-testid="stHorizontalBlock"]
        [data-testid="stMarkdownContainer"] {
            text-align: center !important;
        }

        /* 수정 버튼 파란색 */
        div[class*="st-key-edit_"] button {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            color: white !important;
            min-height: 32px !important;
            padding: 0.1rem 0.25rem !important;
            border-radius: 6px !important;
        }

        div[class*="st-key-edit_"] button:hover {
            background-color: #1d4ed8 !important;
            border-color: #1d4ed8 !important;
        }

        /* 삭제 버튼 빨간색 */
        div[class*="st-key-delete_"] button {
            background-color: #dc2626 !important;
            border-color: #dc2626 !important;
            color: white !important;
            min-height: 32px !important;
            padding: 0.1rem 0.25rem !important;
            border-radius: 6px !important;
        }

        div[class*="st-key-delete_"] button:hover {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
        }

        /* 관리 버튼 사이 간격 축소 */
        div[class*="st-key-manage_"]
        div[data-testid="stVerticalBlock"] {
            gap: 4px !important;
        }

        </style>
    """, unsafe_allow_html=True)
    
    st.write(
        "등록된 학업 일정을 자동 우선순위 순서로 확인합니다."
    )

    # 수정 및 삭제 완료 메시지
    action_message = st.session_state.pop(
        "action_message",
        None
    )

    if action_message is not None:

        if action_message["kind"] == "edit":

            st.success(
                "일정이 정상적으로 수정되었습니다."
            )

            st.info(
                f"수정된 D-Day: "
                f"{format_dday(action_message['dday'])} | "
                f"자동 우선순위 점수: "
                f"{action_message['priority']}"
            )

        elif action_message["kind"] == "delete":

            st.success(
                "일정이 정상적으로 삭제되었습니다."
            )

    schedules = load_schedules()

    if schedules:

        # 각 열의 너비
        widths = [
            0.7, 1.4, 2.0, 1.3, 0.9,
            0.8, 1.2, 1.2, 1.3
        ]

        headers = [
            "순위", "과목명", "일정명", "마감일",
            "D-Day", "중요도", "예상시간",
            "우선순위","관리"
        ]

        # ==========================================
        # 표 제목 - 가운데 정렬만 적용
        # ==========================================
        header_cols = st.columns(
            widths,
            gap=None
        )

        for col, header in zip(header_cols, headers):

            with col:

                st.markdown(
                    f"""
                    <div style="
                        text-align:center;
                        padding:12px 4px;
                        font-weight:bold;
                    ">
                        {escape(header)}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        # ==========================================
        # 1위 일정 위 가로 구분선
        # ==========================================
        st.markdown(
            "<hr style='border:0; border-top:1px solid #d1d5db; margin:0;'>",
            unsafe_allow_html=True
        )

        # ==========================================
        # 일정별 행
        # ==========================================
        for index, schedule in enumerate(
            schedules,
            start=1
        ):

            cols = st.columns(
                widths,
                gap=None,
                vertical_alignment="center"
            )

            values = [
                f"{index}위",
                schedule["과목명"],
                schedule["일정명"],
                schedule["마감일"],
                format_dday(schedule["D-Day"]),
                schedule["중요도"],
                format_expected_time(
                    schedule["예상 소요시간"]
                ),
                str(schedule["우선순위 점수"])
            ]

            # ======================================
            # 일정 내용 가운데 정렬 및 세로 구분선
            # ======================================
            for i, (col, value) in enumerate(
                zip(cols[:8], values)
            ):

                with col:

                    # 우선순위와 관리 사이 구분선 제거
                    border_right = (
                        "none"
                        if i == 7
                        else "1px solid #d1d5db"
                    )

                    st.markdown(
                        f"""
                        <div style="
                            display:flex;
                            align-items:center;
                            justify-content:center;
                            text-align:center;
                            height:76px;
                            padding:4px;
                            box-sizing:border-box;
                            border-right:{border_right};
                            overflow-wrap:anywhere;
                        ">
                            {escape(str(value))}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            # ======================================
            # 관리 버튼 (수정 / 삭제)
            # ======================================
            with cols[8]:

                with st.container(
                    key=f"manage_{schedule['id']}"
                ):

                    # 수정 버튼
                    if st.button(
                        "수정",
                        key=f"edit_{schedule['id']}",
                        width="stretch"
                    ):
                        edit_schedule_dialog(schedule)

                    # 삭제 버튼
                    if st.button(
                        "삭제",
                        key=f"delete_{schedule['id']}",
                        width="stretch"
                    ):
                        delete_schedule_dialog(schedule)

            # ======================================
            # 일정 사이 가로 구분선
            # ======================================
            st.markdown(
                "<hr style='border:0; border-top:1px solid #d1d5db; margin:0;'>",
                unsafe_allow_html=True
            )

    else:

        st.info(
            "현재 등록된 일정이 없습니다."
        )


# ==================================================
# DB 연결 종료
# ==================================================
conn.close()