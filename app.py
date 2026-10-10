import sqlite3
from datetime import date, datetime

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
# 데이터베이스 연결
# ==================================================
conn = sqlite3.connect("schedule.db")
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
# 예상 소요시간 상태 초기화
# ==================================================
if "time_hours" not in st.session_state:
    st.session_state.time_hours = 1


# ==================================================
# 시간 입력값 읽기
# ==================================================
def get_time_hours():

    try:

        hours_text = st.session_state.get(
            "hours_input",
            ""
        ).strip()

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

    hours += amount

    hours = max(
        0,
        min(100, hours)
    )

    st.session_state.time_hours = hours
    st.session_state.hours_input = str(hours)


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
        "일정 목록",
        "일정 수정"
    ]
)


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
    st.write(
        "예상 소요시간"
    )

    if "hours_input" not in st.session_state:

        st.session_state.hours_input = str(
            st.session_state.time_hours
        )

    st.write(
        "시간"
    )

    input_col, minus_col, plus_col = st.columns(
        [5, 1, 1],
        gap="small"
    )

    with input_col:

        st.text_input(
            "시간 입력",
            key="hours_input",
            label_visibility="collapsed"
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

    current_hours = get_time_hours()

    st.session_state.time_hours = current_hours

    expected_time = current_hours


    # ==============================================
    # 일정 등록 버튼
    # ==============================================
    if st.button(
        "일정 등록",
        type="primary"
    ):

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
elif menu == "일정 목록":

    st.header(
        "일정 목록"
    )

    st.write(
        "등록된 학업 일정을 "
        "자동 우선순위 순서로 확인합니다."
    )

    schedules = load_schedules()

    if schedules:

        display_data = []

        for index, schedule in enumerate(
            schedules,
            start=1
        ):

            display_data.append({
                "순위": f"{index}위",
                "과목명": schedule["과목명"],
                "일정명": schedule["일정명"],
                "마감일": schedule["마감일"],
                "D-Day": format_dday(
                    schedule["D-Day"]
                ),
                "중요도": schedule["중요도"],
                "예상 소요시간": format_expected_time(
                    schedule["예상 소요시간"]
                ),
                "우선순위 점수": str(schedule["우선순위 점수"])
            })

        
        st.markdown(
            """
            <style>
            div[data-testid="stTable"] table {
                width: 100%;
                font-size: 15px;
            }

            div[data-testid="stTable"] th {
                text-align: center;
                font-weight: bold;
                padding: 12px 10px;
                white-space: nowrap;
            }

            div[data-testid="stTable"] td {
                text-align: center;
                vertical-align: middle;
                padding: 10px;
                white-space: nowrap;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.table(
            display_data
        )

    else:

        st.info(
            "현재 등록된 일정이 없습니다."
        )

# ==================================================
# 일정 수정
# ==================================================
elif menu == "일정 수정":

    st.header(
        "일정 수정"
    )

    st.write(
        "등록된 학업 일정을 선택하여 수정합니다."
    )

    schedules = load_schedules()

    if schedules:

        # 수정할 일정 선택
        schedule_options = {
            f"{schedule['과목명']} - {schedule['일정명']} "
            f"({format_dday(schedule['D-Day'])})": schedule
            for schedule in schedules
        }

        selected_label = st.selectbox(
            "수정할 일정 선택",
            list(schedule_options.keys())
        )

        selected_schedule = schedule_options[
            selected_label
        ]

        st.divider()

        # 기존 정보 불러오기
        edit_subject = st.text_input(
            "과목명",
            value=selected_schedule["과목명"],
            key=f"edit_subject_{selected_schedule['id']}"
        )

        edit_schedule_name = st.text_input(
            "일정명",
            value=selected_schedule["일정명"],
            key=f"edit_schedule_name_{selected_schedule['id']}"
        )

        edit_deadline = st.date_input(
            "마감일",
            value=datetime.strptime(
                selected_schedule["마감일"],
                "%Y-%m-%d"
            ).date(),
            key=f"edit_deadline_{selected_schedule['id']}"
        )

        importance_options = [
            "높음",
            "보통",
            "낮음"
        ]

        edit_importance = st.selectbox(
            "중요도",
            importance_options,
            index=importance_options.index(
                selected_schedule["중요도"]
            ),
            key=f"edit_importance_{selected_schedule['id']}"
        )

        edit_expected_time = st.number_input(
            "예상 소요시간",
            min_value=1,
            max_value=100,
            value=max(
                1,
                int(
                    selected_schedule[
                        "예상 소요시간"
                    ]
                )
            ),
            step=1,
            format="%d",
            key=f"edit_expected_time_{selected_schedule['id']}"
        )

        st.write(
            f"현재 D-Day: "
            f"{format_dday(selected_schedule['D-Day'])}"
        )

        st.write(
            f"현재 우선순위 점수: "
            f"{selected_schedule['우선순위 점수']}"
        )

        # ==============================================
        # 일정 수정 버튼
        # ==============================================
        if st.button(
            "일정 수정",
            type="primary"
        ):

            if not edit_subject.strip():

                st.warning(
                    "과목명을 입력해주세요."
                )

            elif not edit_schedule_name.strip():

                st.warning(
                    "일정명을 입력해주세요."
                )

            elif (
                edit_subject.strip()
                == selected_schedule["과목명"]

                and edit_schedule_name.strip()
                == selected_schedule["일정명"]

                and edit_deadline.strftime(
                    "%Y-%m-%d"
                )
                == selected_schedule["마감일"]

                and edit_importance
                == selected_schedule["중요도"]

                and int(edit_expected_time)
                == int(
                    selected_schedule[
                        "예상 소요시간"
                    ]
                )
            ):

                st.warning(
                    "기존 일정과 동일합니다. "
                    "수정할 내용을 변경해주세요."
                )

            else:

                cursor.execute("""
                    UPDATE schedules
                    SET
                        subject = ?,
                        schedule_name = ?,
                        deadline = ?,
                        importance = ?,
                        expected_time = ?
                    WHERE id = ?
                """, (
                    edit_subject.strip(),
                    edit_schedule_name.strip(),
                    edit_deadline.strftime(
                        "%Y-%m-%d"
                    ),
                    edit_importance,
                    edit_expected_time,
                    selected_schedule["id"]
                ))

                conn.commit()

                # 수정된 마감일 기준 D-Day 재계산
                new_dday = (
                    edit_deadline
                    - date.today()
                ).days

                # 수정된 중요도, 예상 소요시간 기준
                # 우선순위 점수 재계산
                new_priority = calculate_priority(
                    new_dday,
                    edit_importance,
                    edit_expected_time
                )

                st.success(
                    "일정이 정상적으로 수정되었습니다."
                )

                st.info(
                    f"수정된 D-Day: "
                    f"{format_dday(new_dday)} | "
                    f"자동 우선순위 점수: "
                    f"{new_priority}"
                )
    else:
        st.info(
            "수정할 일정이 없습니다."
        )
# ==================================================
# DB 연결 종료
# ==================================================
conn.close()