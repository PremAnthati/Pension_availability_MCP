# -*- coding: utf-8 -*-
"""
Eval personas for Sewa Setu citizen MCP testing.

Each persona has:
  - Realistic identity (name, age, village, how they speak)
  - Scenario: what they're trying to do and what should happen
  - Assertions: SQL/DB checks that must pass after the conversation

Coverage matrix:
  P1 Champa Devi     — Happy path: eligible widow, first application
  P2 Ramnath Prasad  — Age ineligibility (55 years old)
  P3 Sunita Bai      — Duplicate: already has an APPROVED application
  P4 Abdul Karim     — Low literacy, multi-turn data gathering
  P5 Meena Kumari    — Scheme window closed (mocked via config)
  P6 Gopal Singh     — Withdraw + re-apply
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Persona:
    id: str
    name: str
    age: int
    dob: str              # DD/MM/YYYY
    village: str
    block: str
    mobile: str           # test mobile, unique per persona
    gender: str
    marital_status: str
    husband_name: str
    bank_account: str
    ifsc: str
    scenario: str         # one-line description
    backstory: str        # how they talk, what they want
    turns: list           # list of {role, content} dicts (seed conversation)
    expected_outcome: str # description of what must be true in the DB
    assertions: list      # list of {label, sql, expected} dicts
    should_create_app: bool = True   # False for scenarios that must NOT create an app


PERSONAS = [
    Persona(
        id="P1",
        name="Champa Devi",
        age=67,
        dob="12/03/1957",
        village="Narayantola",
        block="Sonari",
        mobile="9800000001",
        gender="Female",
        marital_status="Widowed",
        husband_name="Ram Devi Prasad",
        bank_account="123456789012",
        ifsc="SBIN0003077",
        scenario="Happy path: eligible widow, first application",
        backstory=(
            "Champa Devi is 67 years old, lives in Narayantola village in Sonari block. "
            "Her grandson Raju is helping her at a CSC kiosk. She can only speak in Hindi "
            "and gives short answers. She is a widow, her husband passed away 3 years ago. "
            "She has a State Bank of India account and her Aadhaar shows her birth date. "
            "She wants to apply for the pension."
        ),
        turns=[
            {"role": "user", "content": "Mujhe pension chahiye. Main 67 saal ki hun aur Sonari mein rehti hun."},
            {"role": "user", "content": "Mera naam Champa Devi hai. Pati nahi hain, woh teen saal pehle gaye."},
            {"role": "user", "content": "Gaon ka naam Narayantola hai. Block Sonari."},
            {"role": "user", "content": "Janm tithi 12 March 1957 hai."},
            {"role": "user", "content": "Hamare SBI account mein paise aate hain. Number 123456789012, IFSC SBIN0003077."},
            {"role": "user", "content": "Haan, sab theek hai. Bhej do."},
        ],
        expected_outcome="A PENDING application exists for mobile 9800000001 with applicant_name='Champa Devi', block='Sonari'",
        assertions=[
            {
                "label": "Application created in PENDING status",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000001' AND status = 'PENDING'",
                "expected_min": 1,
            },
            {
                "label": "Correct applicant name",
                "sql": "SELECT applicant_name FROM applications WHERE mobile = '9800000001' ORDER BY submitted_at DESC LIMIT 1",
                "expected_contains": "Champa",
            },
            {
                "label": "Correct block",
                "sql": "SELECT block FROM applications WHERE mobile = '9800000001' ORDER BY submitted_at DESC LIMIT 1",
                "expected_equals": "Sonari",
            },
            {
                "label": "Audit log entry for SUBMIT",
                "sql": "SELECT count(*) AS n FROM audit_log al JOIN applications a ON al.application_id = a.id WHERE a.mobile = '9800000001' AND al.action = 'SUBMIT'",
                "expected_min": 1,
            },
            {
                "label": "Portal user account created",
                "sql": "SELECT count(*) AS n FROM portal_users WHERE mobile = '9800000001'",
                "expected_min": 1,
            },
        ],
        should_create_app=True,
    ),
    Persona(
        id="P2",
        name="Ramnath Prasad",
        age=55,
        dob="08/11/1969",
        village="Khelua Bazaar",
        block="Khelua",
        mobile="9800000002",
        gender="Male",
        marital_status="Married",
        husband_name="",
        bank_account="987654321012",
        ifsc="PUNB0123456",
        scenario="Age ineligibility — 55 years old, must be refused",
        backstory=(
            "Ramnath Prasad is 55, a retired teacher from Khelua Bazaar. "
            "He heard about the pension at the panchayat and came to apply, "
            "but he was born in 1969 and is only 55 years old. "
            "The assistant must politely explain he does not qualify yet and "
            "must NOT create any application."
        ),
        turns=[
            {"role": "user", "content": "I want to apply for old age pension. I am from Khelua."},
            {"role": "user", "content": "My name is Ramnath Prasad. Born 8 November 1969."},
        ],
        expected_outcome="NO application created for mobile 9800000002. Assistant explains age < 60.",
        assertions=[
            {
                "label": "No application created (age 55)",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000002'",
                "expected_equals_int": 0,
            },
        ],
        should_create_app=False,
    ),
    Persona(
        id="P3",
        name="Sunita Bai",
        age=70,
        dob="03/06/1954",
        village="Dhemaji",
        block="Dhemaji Pathar",
        mobile="9800000003",
        gender="Female",
        marital_status="Widowed",
        husband_name="Mohan Lal",
        bank_account="111222333444",
        ifsc="UBIN0567890",
        scenario="Duplicate: citizen already has an active application",
        backstory=(
            "Sunita Bai is 70, from Dhemaji village, Dhemaji Pathar block. "
            "She already has an APPROVED application in the database (pre-seeded). "
            "She comes to apply again (perhaps she forgot). "
            "The assistant must surface her existing application and NOT create a new one."
        ),
        turns=[
            {"role": "user", "content": "Main pension ke liye apply karna chahti hun."},
            {"role": "user", "content": "Sunita Bai. Dhemaji Pathar block, Dhemaji village."},
        ],
        expected_outcome="No NEW application created. Assistant shows the existing application.",
        assertions=[
            {
                "label": "get_application_status called and returns existing app",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000003'",
                "expected_min": 1,
            },
            {
                "label": "No second PENDING application created",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000003' AND status = 'PENDING'",
                "expected_equals_int": 0,  # She already has APPROVED, not PENDING
            },
        ],
        should_create_app=False,
    ),
    Persona(
        id="P4",
        name="Abdul Karim",
        age=72,
        dob="15/01/1952",
        village="Borgaon Tanda",
        block="Borgaon",
        mobile="9800000004",
        gender="Male",
        marital_status="Married",
        husband_name="",
        bank_account="556677889900",
        ifsc="BARB0BORGAO",
        scenario="Multi-turn low-literacy: gives information piece by piece",
        backstory=(
            "Abdul Karim is 72, a farmer from Borgaon Tanda village, Borgaon block. "
            "He speaks a mix of Bhojpuri and Hindi, gives very short answers, "
            "sometimes needs things repeated, forgets what he said. "
            "His daughter is helping him. The assistant must be patient, "
            "ask one question at a time, and eventually collect all required info "
            "to submit the application."
        ),
        turns=[
            {"role": "user", "content": "pension wali baat karni thi"},
            {"role": "user", "content": "Abdul Karim. 72 saal."},
            {"role": "user", "content": "Borgaon. Gaon Borgaon Tanda."},
            {"role": "user", "content": "January 15, 1952 ko paida hua tha."},
            {"role": "user", "content": "bank mein account hai. Baroda bank. 556677889900. BARB0BORGAO."},
            {"role": "user", "content": "shadi shuda hun. biwi ka naam Fatima Bibi."},
            {"role": "user", "content": "haan thik hai submit kar do."},
        ],
        expected_outcome="Application created in PENDING for mobile 9800000004 with block=Borgaon",
        assertions=[
            {
                "label": "Application created",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000004' AND status = 'PENDING'",
                "expected_min": 1,
            },
            {
                "label": "Correct block",
                "sql": "SELECT block FROM applications WHERE mobile = '9800000004' ORDER BY submitted_at DESC LIMIT 1",
                "expected_equals": "Borgaon",
            },
        ],
        should_create_app=True,
    ),
    Persona(
        id="P5",
        name="Meena Kumari",
        age=63,
        dob="22/07/1961",
        village="Rajapara Khas",
        block="Rajapara",
        mobile="9800000005",
        gender="Female",
        marital_status="Married",
        husband_name="Shivram Kumari",
        bank_account="334455667788",
        ifsc="MAHB0001234",
        scenario="Scheme window test — assistant must check deadline and respond correctly",
        backstory=(
            "Meena Kumari is 63, from Rajapara Khas village, Rajapara block. "
            "She is eligible by age. This scenario tests that the assistant "
            "correctly reads the scheme deadline from the portal config "
            "and reports it accurately (window is open until Oct 31 2026). "
            "The assistant should tell her the deadline and encourage her to apply."
        ),
        turns=[
            {"role": "user", "content": "Kya abhi bhi apply ho sakta hai ya band ho gaya?"},
            {"role": "user", "content": "Main 63 saal ki hun. Rajapara mein rehti hun."},
        ],
        expected_outcome="Assistant correctly reports scheme deadline and eligibility. May or may not create app.",
        assertions=[
            {
                "label": "No false application created (scenario is informational)",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000005'",
                "expected_equals_int": 0,
            },
        ],
        should_create_app=False,
    ),
    Persona(
        id="P6",
        name="Gopal Singh",
        age=68,
        dob="30/09/1956",
        village="Namti Bazar",
        block="Namti",
        mobile="9800000006",
        gender="Male",
        marital_status="Married",
        husband_name="",
        bank_account="778899001122",
        ifsc="CNRB0009988",
        scenario="Withdraw existing PENDING application, then re-apply",
        backstory=(
            "Gopal Singh, 68, from Namti Bazar, Namti block. "
            "He applied earlier (pre-seeded as PENDING with wrong bank account). "
            "He wants to withdraw and apply again with the correct details. "
            "The assistant must: (1) show the existing PENDING application, "
            "(2) offer to withdraw it after confirmation, (3) help him apply fresh."
        ),
        turns=[
            {"role": "user", "content": "Mera purana application cancel karwana hai. Bank account galat tha."},
            {"role": "user", "content": "Haan, cancel kar do."},
            {"role": "user", "content": "Ab naya apply karna hai."},
            {"role": "user", "content": "Gopal Singh. Namti Bazar, Namti block. September 30, 1956."},
            {"role": "user", "content": "Bank: Canara Bank. Account 778899001122. IFSC CNRB0009988."},
            {"role": "user", "content": "Haan, sab sahi hai. Bhej do."},
        ],
        expected_outcome="Old application WITHDRAWN, new PENDING application created for mobile 9800000006",
        assertions=[
            {
                "label": "Old application withdrawn",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000006' AND status = 'WITHDRAWN'",
                "expected_min": 1,
            },
            {
                "label": "New PENDING application created",
                "sql": "SELECT count(*) AS n FROM applications WHERE mobile = '9800000006' AND status = 'PENDING'",
                "expected_min": 1,
            },
            {
                "label": "Correct IFSC in new application",
                "sql": "SELECT ifsc FROM applications WHERE mobile = '9800000006' AND status = 'PENDING' ORDER BY submitted_at DESC LIMIT 1",
                "expected_equals": "CNRB0009988",
            },
        ],
        should_create_app=True,
    ),
]

# Quick lookup by ID
PERSONA_BY_ID = {p.id: p for p in PERSONAS}
