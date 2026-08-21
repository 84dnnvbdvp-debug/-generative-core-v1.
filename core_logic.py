import os
import json
import re
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME")
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

STATE_FILE = "core_state.json"
TARGET_LABELS = {"yield-opportunity", "bounty-request"}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    # Corrected Post-Deployment Ledger ($1.50 TASK-1 + $4.50 TASK-2 = $6.00 Accrued Payout)
    return {
        "capital_reserve_usd": 14.00,
        "available_escrow_usd": 9.00,
        "locked_escrow_usd": 0.00,
        "api_reserve_usd": 5.00,
        "contractor_payout_accrued_usd": 6.00,
        "processed_issues": [],
        "active_locks": {}  # issue_id: locked_amount
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def fetch_open_issues():
    url = f"https://api.github.com/repos/{REPO_NAME}/issues?state=open"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return []
    
    # Python-side OR filtering for labels
    all_issues = res.json()
    relevant_issues = []
    for issue in all_issues:
        issue_labels = {l["name"] for l in issue.get("labels", [])}
        if issue_labels.intersection(TARGET_LABELS):
            relevant_issues.append(issue)
    return relevant_issues

def post_comment(issue_number, comment_text):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{issue_number}/comments"
    requests.post(url, headers=HEADERS, json={"body": comment_text})

def parse_ev_parameters(text):
    payout_match = re.search(r"PAYOUT:\s*\$?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    cost_match = re.search(r"COST:\s*\$?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    prob_match = re.search(r"PROBABILITY:\s*(0?\.\d+|1\.0|1)", text, re.IGNORECASE)

    if payout_match and cost_match:
        payout = float(payout_match.group(1))
        cost = float(cost_match.group(1))
        prob = float(prob_match.group(1)) if prob_match else 0.8
        return payout, cost, prob
    return None

def process_opportunities():
    state = load_state()
    issues = fetch_open_issues()

    for issue in issues:
        issue_id = str(issue["number"])
        if issue_id in state["processed_issues"]:
            continue

        body = issue.get("body", "")
        params = parse_ev_parameters(body)

        if params:
            payout, cost, prob = params
            ev = (prob * payout) - cost

            if ev > 0 and state["available_escrow_usd"] >= cost:
                # Explicit state tracking for locked obligations
                state["available_escrow_usd"] -= cost
                state["locked_escrow_usd"] += cost
                state["active_locks"][issue_id] = cost
                
                response = (
                    f"### 🤖 Core Evaluation: APPROVED & FUNDS LOCKED\n"
                    f"- **Probability of Success:** {prob * 100:.0f}%\n"
                    f"- **Expected Value ($EV):** +${ev:.2f}\n"
                    f"- **Locked Obligation:** ${cost:.2f}\n"
                    f"- **Remaining Unallocated Escrow:** ${state['available_escrow_usd']:.2f}\n"
                    f"- **Status:** Contract locked. Execution authorized."
                )
            else:
                response = (
                    f"### 🤖 Core Evaluation: REJECTED\n"
                    f"- **Probability of Success:** {prob * 100:.0f}%\n"
                    f"- **Expected Value ($EV):** ${ev:.2f}\n"
                    f"- **Required Cost:** ${cost:.2f} (Available Escrow: ${state['available_escrow_usd']:.2f})\n"
                    f"- **Status:** EV <= 0 or insufficient unallocated funds. Task declined."
                )
        else:
            response = (
                "### 🤖 Core Evaluation: INVALID SPECIFICATION\n"
                "Could not parse valid parameters. Required format:\n"
                "```\nPAYOUT: 10.00\nCOST: 2.00\nPROBABILITY: 0.85\n```"
            )

        post_comment(issue["number"], response)
        state["processed_issues"].append(issue_id)

    save_state(state)

if __name__ == "__main__":
    process_opportunities()