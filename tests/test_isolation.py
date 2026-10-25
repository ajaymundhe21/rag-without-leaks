"""pytest -q   (needs the database loaded: see README)"""
import psycopg
from app.config import DATABASE_URL
from app.db import tenant_tx
from app.identity import flatten
from app.ingest import write_document
from app.search import search
from eval.run import leak

Q = "How many weeks of maternity leave do I get?"


def test_groups_are_flattened_at_login():
    assert flatten(["engineering"]) == ["all-staff", "engineering", "product"]


def test_employee_gets_page_12_and_no_board_rows():
    res = search(1, flatten(["engineering"]), Q)
    assert (res[0]["doc_id"], res[0]["page"]) == ("hr/hr-handbook", 12)
    assert not any(c["doc_id"].startswith("board/") for c in res)


def test_leak_questions_return_zero_restricted_rows_for_an_employee():
    assert leak("emp-1")["restricted_rows"] == 0


def test_the_leak_test_can_fail():
    # The same questions as a board member do find the board's pages.
    assert leak("board-1")["questions_that_found_restricted"] > 0


def test_a_query_without_the_tenant_filter_still_sees_one_company():
    with tenant_tx(1) as conn:
        tenants = conn.execute("SELECT DISTINCT tenant_id FROM chunks").fetchall()
    assert tenants == [(1,)]


def test_no_tenant_set_means_no_rows():
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_writing_the_same_document_twice_does_not_duplicate():
    pieces = [(1, "Test doc · Section. Same text twice.")]
    write_document(1, "test/twice", ["all-staff"], pieces)
    write_document(1, "test/twice", ["all-staff"], pieces)
    with tenant_tx(1) as conn:
        n = conn.execute("SELECT count(*) FROM chunks WHERE doc_id = 'test/twice'").fetchone()[0]
        conn.execute("DELETE FROM chunks WHERE doc_id = 'test/twice'")
    assert n == 1

