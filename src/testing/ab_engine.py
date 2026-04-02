"""A/B test tracking + statistical stopping rules — Stage 7.

Rules from CLAUDE.md:
1. Min 10 sends per variant before evaluation
2. After >=30 total replies, compare reply rates
3. Kill if variant reply rate is >=30% below best performer
4. Boost if variant reply rate is >=30% above average
5. Redistribute killed variant weight to survivors
6. Weekly report on dashboard
7. Never kill below 4 active variants
"""

import logging
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from sqlalchemy import func

from src.config import AgentConfig
from src.db.models import OutreachLog, ResponseTracker
from src.db.session import get_session

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class VariantStats:
    variant_id: str
    style: str
    sends: int
    replies: int
    referrals: int
    reply_rate: float
    referral_rate: float
    active: bool
    weight: float


def get_variant_performance() -> list[VariantStats]:
    """Calculate performance stats for all variants."""
    session = get_session()
    try:
        stats = []
        config_variants = AgentConfig.variants

        for vid, vconfig in config_variants.items():
            # Count sends (status = sent or replied)
            sends = session.query(func.count(OutreachLog.id)).filter(
                OutreachLog.variant == vid,
                OutreachLog.status.in_(["sent", "replied"]),
            ).scalar() or 0

            # Count replies
            replies = session.query(func.count(OutreachLog.id)).filter(
                OutreachLog.variant == vid,
                OutreachLog.status == "replied",
            ).scalar() or 0

            # Count referrals
            referrals = session.query(func.count(ResponseTracker.id)).filter(
                ResponseTracker.response_type == "referral",
                ResponseTracker.outreach_id.in_(
                    session.query(OutreachLog.id).filter(OutreachLog.variant == vid)
                ),
            ).scalar() or 0

            reply_rate = (replies / sends * 100) if sends > 0 else 0.0
            referral_rate = (referrals / sends * 100) if sends > 0 else 0.0

            stats.append(VariantStats(
                variant_id=vid,
                style=vconfig.get("style", "unknown"),
                sends=sends,
                replies=replies,
                referrals=referrals,
                reply_rate=round(reply_rate, 1),
                referral_rate=round(referral_rate, 1),
                active=vconfig.get("active", True),
                weight=vconfig.get("weight", 0.1),
            ))

        return sorted(stats, key=lambda s: s.reply_rate, reverse=True)
    finally:
        session.close()


def evaluate_variants() -> dict:
    """Run statistical stopping rules. Returns dict of recommendations.

    Returns:
        {
            "total_sends": int,
            "total_replies": int,
            "can_evaluate": bool,
            "kill": [variant_ids...],
            "boost": [variant_ids...],
            "active_count": int,
        }
    """
    stats = get_variant_performance()
    config = AgentConfig

    total_sends = sum(s.sends for s in stats)
    total_replies = sum(s.replies for s in stats)
    active_stats = [s for s in stats if s.active]
    active_count = len(active_stats)

    result = {
        "total_sends": total_sends,
        "total_replies": total_replies,
        "can_evaluate": False,
        "kill": [],
        "boost": [],
        "active_count": active_count,
    }

    # Rule 2: Need >=30 total replies to evaluate
    if total_replies < config.min_total_replies_to_evaluate:
        return result

    result["can_evaluate"] = True

    # Only evaluate variants with min sends
    evaluable = [s for s in active_stats if s.sends >= config.min_sends_per_variant]
    if not evaluable:
        return result

    # Find best performer and average
    best_rate = max(s.reply_rate for s in evaluable)
    avg_rate = sum(s.reply_rate for s in evaluable) / len(evaluable) if evaluable else 0

    for s in evaluable:
        # Rule 3: Kill if >=30% below best
        if best_rate > 0 and s.reply_rate <= best_rate * (1 - config.kill_threshold_pct / 100):
            # Rule 7: Never kill below 4 active
            if active_count - len(result["kill"]) > config.min_active_variants:
                result["kill"].append(s.variant_id)

        # Rule 4: Boost if >=30% above average
        elif avg_rate > 0 and s.reply_rate >= avg_rate * (1 + config.winner_boost_threshold_pct / 100):
            result["boost"].append(s.variant_id)

    return result


def apply_recommendations(recommendations: dict) -> dict:
    """Apply kill/boost recommendations to variant config.
    Returns updated variant weights dict (for saving to config if desired).
    """
    variants = dict(AgentConfig.variants)

    # Kill underperformers
    for vid in recommendations.get("kill", []):
        if vid in variants:
            variants[vid]["active"] = False
            logger.info(f"Deactivated variant {vid} (underperforming)")

    # Redistribute killed weight
    killed_weight = sum(
        variants[vid].get("weight", 0.1)
        for vid in recommendations.get("kill", [])
        if vid in variants
    )
    active_variants = [vid for vid, v in variants.items() if v.get("active", True)]

    if active_variants and killed_weight > 0:
        bonus = killed_weight / len(active_variants)
        for vid in active_variants:
            variants[vid]["weight"] = round(variants[vid].get("weight", 0.1) + bonus, 4)

    # Boost winners (double weight)
    for vid in recommendations.get("boost", []):
        if vid in variants and variants[vid].get("active", True):
            variants[vid]["weight"] = round(variants[vid].get("weight", 0.1) * 2, 4)
            logger.info(f"Boosted variant {vid} weight to {variants[vid]['weight']}")

    # Normalize weights
    total_weight = sum(v.get("weight", 0.1) for v in variants.values() if v.get("active", True))
    if total_weight > 0:
        for vid, v in variants.items():
            if v.get("active", True):
                v["weight"] = round(v["weight"] / total_weight, 4)

    return variants


def print_ab_report():
    """Print a formatted A/B test report to console."""
    stats = get_variant_performance()
    recommendations = evaluate_variants()

    # Summary
    console.print()
    console.print("[bold cyan]A/B Test Performance Report[/bold cyan]")
    console.print(f"Total sends: {recommendations['total_sends']} | "
                  f"Total replies: {recommendations['total_replies']} | "
                  f"Active variants: {recommendations['active_count']}")

    if not recommendations["can_evaluate"]:
        needed = AgentConfig.min_total_replies_to_evaluate - recommendations["total_replies"]
        console.print(f"[yellow]Need {needed} more replies before statistical evaluation.[/yellow]")

    # Performance table
    table = Table(title="Variant Performance", show_lines=True)
    table.add_column("Variant", style="bold")
    table.add_column("Style")
    table.add_column("Sends", justify="right")
    table.add_column("Replies", justify="right")
    table.add_column("Reply %", justify="right")
    table.add_column("Referrals", justify="right")
    table.add_column("Ref %", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Status")

    for s in stats:
        status = "[green]Active[/green]" if s.active else "[red]Retired[/red]"
        if s.variant_id in recommendations.get("kill", []):
            status = "[red]KILL[/red]"
        elif s.variant_id in recommendations.get("boost", []):
            status = "[green]BOOST[/green]"

        reply_style = ""
        if s.reply_rate > 0:
            reply_style = "green" if s.reply_rate >= 20 else ("yellow" if s.reply_rate >= 10 else "red")

        table.add_row(
            s.variant_id,
            s.style,
            str(s.sends),
            str(s.replies),
            f"[{reply_style}]{s.reply_rate}%[/{reply_style}]" if reply_style else f"{s.reply_rate}%",
            str(s.referrals),
            f"{s.referral_rate}%",
            f"{s.weight:.2f}",
            status,
        )

    console.print(table)

    # Recommendations
    if recommendations.get("kill"):
        console.print(f"\n[red]Recommend killing:[/red] {', '.join(recommendations['kill'])}")
    if recommendations.get("boost"):
        console.print(f"[green]Recommend boosting:[/green] {', '.join(recommendations['boost'])}")
    console.print()
