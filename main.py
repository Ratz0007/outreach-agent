"""CLI entry point for the Job Search Execution Agent."""

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="outreach-agent",
    help="Job Search Execution Agent — automate your job search pipeline.",
    add_completion=False,
)
console = Console()


def _init():
    """Initialize database on every CLI invocation."""
    from src.db.session import init_db
    init_db()


@app.command()
def run():
    """Run the full daily pipeline (all stages sequentially)."""
    _init()
    console.print(Panel("Running full daily pipeline...", style="bold green"))
    source()
    enrich()
    generate()
    send()
    check_replies()
    digest()
    console.print("[bold green]Daily pipeline complete.[/bold green]")


@app.command()
def source():
    """Stage 1: Job sourcing (Adzuna API + CSV import)."""
    _init()
    console.print("[cyan]Running Stage 1: Job Sourcing...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.sourcing.adzuna import source_jobs
            count = source_jobs()
            console.print(f"[green]Sourced {count} new jobs.[/green]")
    finally:
        session.close()


@app.command()
def enrich():
    """Stage 2: Contact enrichment via Apollo.io."""
    _init()
    console.print("[cyan]Running Stage 2: Contact Enrichment...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.enrichment.apollo import enrich_contacts
            count = enrich_contacts()
            console.print(f"[green]Enriched contacts for {count} jobs.[/green]")
    finally:
        session.close()


@app.command()
def generate():
    """Stage 3: Generate personalised message drafts via Claude API."""
    _init()
    console.print("[cyan]Running Stage 3: Message Generation...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.messaging.generator import generate_messages
            count = generate_messages()
            console.print(f"[green]Generated {count} message drafts.[/green]")
    finally:
        session.close()


@app.command()
def send():
    """Stage 4: Send approved messages (Gmail + LinkedIn copy-paste)."""
    _init()
    console.print("[cyan]Running Stage 4: Outreach Execution...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.outreach.gmail import send_approved_emails
            email_count = send_approved_emails()
            console.print(f"[green]Sent {email_count} emails.[/green]")
            console.print("[yellow]Check dashboard for LinkedIn messages to copy-paste.[/yellow]")
    finally:
        session.close()


@app.command(name="check-replies")
def check_replies():
    """Stage 5: Process responses (Gmail replies + LinkedIn)."""
    _init()
    console.print("[cyan]Running Stage 5: Response Handling...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.tracking.response_handler import check_and_classify_replies
            count = check_and_classify_replies()
            console.print(f"[green]Processed {count} replies.[/green]")
    finally:
        session.close()


@app.command()
def tailor(
    job_id: int = typer.Argument(..., help="Job ID to tailor CV for"),
    no_cover: bool = typer.Option(False, "--no-cover", help="Skip cover letter generation"),
):
    """Stage 6: Tailor CV + cover letter for a specific job."""
    _init()
    console.print(f"[cyan]Running Stage 6: CV Tailoring for job {job_id}...[/cyan]")
    from src.cv.tailor import tailor_cv
    result = tailor_cv(job_id, generate_cover=not no_cover)
    console.print(f"[green]Region: {result['region']}[/green]")
    console.print(f"[green]CV saved: {result['cv_path']}[/green]")
    if result.get("cover_letter_path"):
        console.print(f"[green]Cover letter saved: {result['cover_letter_path']}[/green]")
    console.print(f"[dim]Keywords used: {', '.join(result['keywords'][:8])}...[/dim]")


@app.command(name="ab-report")
def ab_report():
    """Stage 7: Print A/B test performance report."""
    _init()
    console.print("[cyan]Running Stage 7: A/B Test Report...[/cyan]")
    from src.testing.ab_engine import print_ab_report
    print_ab_report()


@app.command()
def digest():
    """Stage 8: Send daily digest email."""
    _init()
    console.print("[cyan]Running Stage 8: Daily Digest...[/cyan]")
    from src.db.session import get_session
    from src.db.models import User
    from src.config import current_user_id
    session = get_session()
    try:
        for u in session.query(User).filter(User.is_active == True).all():
            current_user_id.set(u.id)
            console.print(f"\\n[bold magenta]--- Executing for User: {u.username} ---[/bold magenta]")
            from src.digest.daily import send_daily_digest
            send_daily_digest()
            console.print("[green]Daily digest sent.[/green]")
    finally:
        session.close()


@app.command()
def dashboard():
    """Start the web dashboard at localhost:8000."""
    _init()
    console.print("[bold cyan]Starting dashboard at http://localhost:8000[/bold cyan]")
    import uvicorn
    uvicorn.run("src.dashboard.app:app", host="0.0.0.0", port=8000, reload=True)


@app.command(name="import-csv")
def import_csv(
    file: str = typer.Argument(..., help="Path to CSV file"),
    source_name: str = typer.Option("linkedin", "--source", "-s", help="Source: linkedin/irishjobs"),
):
    """Import jobs from a CSV file (LinkedIn/IrishJobs export)."""
    _init()
    console.print(f"[cyan]Importing from {file} (source: {source_name})...[/cyan]")
    from src.sourcing.csv_import import import_jobs_csv
    count = import_jobs_csv(file, source_name)
    console.print(f"[green]Imported {count} jobs.[/green]")


@app.command()
def seed():
    """Seed the database with test data for development."""
    _init()
    console.print("[cyan]Seeding database with test data...[/cyan]")
    from src.db.seed import seed_test_data
    seed_test_data()
    console.print("[green]Test data seeded successfully.[/green]")


@app.command(name="gmail-auth")
def gmail_auth():
    """Run Gmail OAuth2 setup flow to get refresh token."""
    console.print("[cyan]Starting Gmail OAuth2 setup...[/cyan]")
    from src.outreach.gmail import run_gmail_auth_flow
    run_gmail_auth_flow()


@app.command()
def quota():
    """Show LinkedIn invite quota status."""
    _init()
    from src.outreach.linkedin import get_linkedin_quota_status
    q = get_linkedin_quota_status()
    console.print(Panel(
        f"[bold]Daily:[/bold]  {q['daily_sent']}/{q['daily_limit']} sent ({q['daily_remaining']} remaining)\\n"
        f"[bold]Weekly:[/bold] {q['weekly_sent']}/{q['weekly_limit']} sent ({q['weekly_remaining']} remaining)\\n"
        f"[bold]Can send:[/bold] {'Yes' if q['can_send'] else '[red]NO — limit reached[/red]'}\\n\\n"
        f"[dim]Mode: Manual copy-paste (LinkedIn API not available)[/dim]",
        title="LinkedIn Quota Status",
        style="cyan"
    ))


@app.command()
def stats():
    """Print quick stats to terminal."""
    _init()
    from src.db.session import get_session
    from src.db.models import JobShortlist, PeopleMapper, OutreachLog, ResponseTracker
    from sqlalchemy import func

    session = get_session()
    try:
        jobs = session.query(func.count(JobShortlist.id)).scalar()
        contacts = session.query(func.count(PeopleMapper.id)).scalar()
        drafts = session.query(func.count(OutreachLog.id)).filter(OutreachLog.status == "draft").scalar()
        sent = session.query(func.count(OutreachLog.id)).filter(OutreachLog.status == "sent").scalar()
        replies = session.query(func.count(ResponseTracker.id)).scalar()

        console.print(Panel(
            f"[bold]Jobs:[/bold] {jobs}\\n"
            f"[bold]Contacts:[/bold] {contacts}\\n"
            f"[bold]Drafts:[/bold] {drafts}\\n"
            f"[bold]Sent:[/bold] {sent}\\n"
            f"[bold]Replies:[/bold] {replies}",
            title="Quick Stats",
            style="cyan"
        ))
    finally:
        session.close()


if __name__ == "__main__":
    app()
