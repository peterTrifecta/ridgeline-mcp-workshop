# Ridgeline Outfitters — Terms Policy

The rules our sales team works to. Every one of them is enforced by the Pricing &
Credit service (`pricing_service.py` in this workshop), not by whoever is asking.

## Contract pricing

Each account has a tier, and the tier sets the price off our list price:

| Tier | Contract price |
|---|---|
| Gold | 10% off list |
| Silver | 5% off list |
| Bronze | List price |

Unit prices are rounded to the cent after each discount. The line total is the
unit price times the quantity.

## Account standing

Standing comes from the most past-due open invoice on the account:

| Standing | When |
|---|---|
| **Good** | Nothing more than 30 days past due |
| **Watch** | The most past-due invoice is 31–60 days past due |
| **Credit hold** | Anything more than 60 days past due |

Credit hold is applied automatically by this rule. Nobody sets it by hand.

## Credit

Available credit = credit limit − open invoice balance.

An order placed on terms has to fit inside available credit. If it doesn't, the
customer can prepay, or we ship part of it now and the rest once the balance
comes down.

Credit limits are owned by finance in the ERP. Salesforce holds a read-only copy.

## Payment terms

- **Net 30** is the default, for accounts in Good or Watch standing.
- **Net 60** only when all three are true: Gold tier, Good standing, and the
  order fits available credit.
- **Credit hold: prepay only.**

## Extra discounts

An extra discount is anything on top of the contract price. Available to
accounts in Good or Watch standing.

| Discount | What happens |
|---|---|
| Up to 10% | Auto-approved |
| Over 10%, up to 20% | Needs sales manager approval (Laura Bennett) |
| Over 20% | Refused |

**Accounts on credit hold get no extra discounts.**

## AI-specific guardrails

These are rules about the AI, not about the business, so they live in the MCP
layer (`ridgeline_tools.py`) rather than in the service:

- The AI must get explicit confirmation from the user before it submits a
  discount request. It never submits one on its own initiative.
- The AI can auto-approve only up to **5%**, even though the policy above lets a
  sales rep auto-approve up to 10%. Anything between 5% and 10% goes to the
  account's sales rep for a one-click OK. Manager approval over 10% is unchanged.

The second rule is the one we add on stage. Note what it is not: it is not the AI
being asked nicely to behave. The limit is handed to the service, and the service
assigns the status.
