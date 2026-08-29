#!/usr/bin/env python3
"""Create a human survey campaign and write one-time invites to a private CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.survey import SurveyCampaignCreateRequest
from app.services.survey_service import SurveyService


DEFAULT_ROLES = ["business", "risk", "product", "operations", "compliance", "technology"]
DEFAULT_SCENARIOS = ["credit_risk", "customer_marketing", "operation_management"]


def write_invitation_csv(path: Path, campaign_id: str, tokens: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite invitation file: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["campaign_id", "invitation_token", "assigned_to", "distributed_at"],
        )
        writer.writeheader()
        for token in tokens:
            writer.writerow(
                {
                    "campaign_id": campaign_id,
                    "invitation_token": token,
                    "assigned_to": "",
                    "distributed_at": "",
                }
            )


def create_campaign_artifacts(
    service: SurveyService,
    request: SurveyCampaignCreateRequest,
    invitation_dir: Path,
) -> tuple[str, Path]:
    campaign, tokens = service.create_campaign(request)
    output = invitation_dir / f"{campaign.campaign_id}_invitations.private.csv"
    write_invitation_csv(output, campaign.campaign_id, tokens)
    return campaign.campaign_id, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a standardized human survey campaign")
    parser.add_argument("--name", required=True)
    parser.add_argument("--invite-count", type=int, default=50)
    parser.add_argument("--minimum-respondents", type=int, default=30)
    parser.add_argument("--samples-per-respondent", type=int, default=2)
    parser.add_argument("--acceptance-test", action="store_true")
    parser.add_argument("--invitation-dir", default="data/surveys/invitations")
    args = parser.parse_args()

    request = SurveyCampaignCreateRequest(
        name=args.name,
        invite_count=args.invite_count,
        minimum_respondents=args.minimum_respondents,
        samples_per_respondent=args.samples_per_respondent,
        required_roles=DEFAULT_ROLES,
        required_scenarios=DEFAULT_SCENARIOS,
        evidence_mode="acceptance_test" if args.acceptance_test else "human_survey",
    )
    invitation_dir = Path(args.invitation_dir)
    if not invitation_dir.is_absolute():
        invitation_dir = ROOT / invitation_dir
    campaign_id, output = create_campaign_artifacts(SurveyService(), request, invitation_dir.resolve())
    print(f"Campaign created: {campaign_id}")
    print(f"Private invitation file: {output}")
    print("Invitation tokens were written once and were not printed to the console.")


if __name__ == "__main__":
    main()
