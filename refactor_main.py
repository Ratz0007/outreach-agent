import re
from pathlib import Path

def wrap_with_mt(content, func_name, stage_name, inner_call_regex, success_msg_regex):
    pattern = rf"(@app\.command\([^\)]*\)\s+def {func_name}\([^\)]*\):\s+\"\"\"[^\"]+\"\"\"\s+_init\(\)\s+console\.print\([^)]+\)\n)" \
              rf"(\s+from src\.[a-zA-Z0-9_\.]+ import [a-zA-Z0-9_]+\n)(\s+{inner_call_regex}\n\s+{success_msg_regex}\n)"
    
    wrapper = r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    
    session = get_session()
    try:
        users = session.query(User).filter(User.is_active == True).all()
        for u in users:
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\2\3
    finally:
        session.close()
"""
    return re.sub(pattern, r"\1" + wrapper.replace("\\2", r"\2").replace("\\3", r"\3"), content)


def refactor_main_py():
    main_py_path = Path("main.py")
    content = main_py_path.read_text("utf-8")
    
    # 1. source
    content = re.sub(
        r"(\s+from src\.sourcing\.adzuna import source_jobs\n\s+count = source_jobs\(\)\n\s+console\.print\(f\"\[green\]Sourced \{count\} new jobs\.\[/green\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    # 2. enrich
    content = re.sub(
        r"(\s+from src\.enrichment\.apollo import enrich_contacts\n\s+count = enrich_contacts\(\)\n\s+console\.print\(f\"\[green\]Enriched contacts for \{count\} jobs\.\[/green\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    # 3. generate
    content = re.sub(
        r"(\s+from src\.messaging\.generator import generate_messages\n\s+count = generate_messages\(\)\n\s+console\.print\(f\"\[green\]Generated \{count\} message drafts\.\[/green\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    # 4. send
    content = re.sub(
        r"(\s+from src\.outreach\.gmail import send_approved_emails\n\s+email_count = send_approved_emails\(\)\n\s+console\.print\(f\"\[green\]Sent \{email_count\} emails\.\[/green\]\"\)\n\s+console\.print\(\"\[yellow\]Check dashboard for LinkedIn messages to copy-paste\.\[/yellow\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    # 5. check_replies
    content = re.sub(
        r"(\s+from src\.tracking\.response_handler import check_and_classify_replies\n\s+count = check_and_classify_replies\(\)\n\s+console\.print\(f\"\[green\]Processed \{count\} replies\.\[/green\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    # 8. digest
    content = re.sub(
        r"(\s+from src\.digest\.daily import send_daily_digest\n\s+send_daily_digest\(\)\n\s+console\.print\(\"\[green\]Daily digest sent\.\[/green\]\"\))",
        r"""
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")\1
    finally:
        session.close()""",
        content
    )

    main_py_path.write_text(content, "utf-8")
    print("Refactored main.py successfully!")

if __name__ == "__main__":
    refactor_main_py()
