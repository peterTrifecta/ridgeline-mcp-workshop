# Walkthrough

A step-by-step script for running the workshop: what to do, what to type and
what to expect at each step. Every prompt below is also in
[`snippets/prompts.txt`](snippets/prompts.txt), in order, to paste from.

Each step's end state is the next step's start state, so run straight through.
Reset once before step 1. After that the only things you touch are the
**Tools** toggle, the pasted snippets and **New conversation**. `uv run reset N`
is for recovery; see *If an edit goes wrong*.

## Before you start

```bash
cd ridgeline-mcp-workshop
uv run check        # every line must say PASS
uv run reset 1      # loads step 1 and rebuilds the data
uv run start        # opens the chat page
```

`uv run check` takes about 15 seconds and makes one tiny API call to confirm
the key works. If a line says FAIL, fix that before starting.

Have these open in the editor:

- `ridgeline_tools.py`, the file you edit
- `pricing_service.py`, the file you point at and never edit
- `snippets/step3_check_contract_pricing.py`
- `snippets/step4_get_open_invoices.py`
- `snippets/step5a_ai_auto_approve_limit.py`
- `snippets/step5b_pass_the_limit.py`
- `snippets/prompts.txt`

The **A+** button in the page header enlarges the text.

### If an edit goes wrong

`uv run reset N+1` loads the next step's starting state, which is the same as
the end of step N, and rebuilds the data. You lose only the edit. Resetting
while the app is running is fine. Then click **New conversation**.

---

## Step 1: No tools

The Tools toggle starts **off**. Nothing to edit.

**Type:**

> Summit Trail Co. wants 15% off a 200-unit order of the TrailLite 2P tent, on net 60 terms. Can we do that?

**Expect:** no tool calls and no numbers. Claude says it cannot confirm, lists
what it would need (the price, the discount tiers, whether net 60 is standard
for this account, who signs off) and offers to run the numbers if it is
connected to the pricing system. It does not make up a price or an approver.

---

## Step 2: Connect the server

**Do:** flip **Tools on** in the header. Click **New conversation**.

**Type:** the same question.

**Expect tool calls:** `find_account`, `list_products`,
`check_credit_availability`. It does not call `check_contract_pricing`; the
description it has for that tool is the vague one, which step 3 fixes.

**Expect answer:** the account details are correct: Gold tier, Good standing,
$112,000 available credit, currently on net 30, net 60 allowed for this order,
rep Dana Ruiz. The price is Claude's own arithmetic off the $249 list price:
$49,800 for 200 units, about $42,330 with 15% off. It usually notes that it
used list price because it has no contract price. It asks whether to submit
the request.

The contract price is $224.10 and the correct total is $38,098.00. That number
comes at step 3.

**Do:** click **tools/list** in the header. The JSON is what the model
receives: a name, a description and the argument schema for each tool.

---

## Step 3: Fix the vague description

Nothing to type first. Step 2's answer is on screen and the price is wrong.

In `ridgeline_tools.py`, find the tool marked `# ---- STEP 3 ----`:

```python
@mcp.tool()
def check_contract_pricing(a: str, b: str, c: int, d: float = 0) -> dict:
    """Legacy batch job. Used by the nightly reconciliation run only."""
```

Nothing in that description says this is how to price an order, and the
argument names say nothing at all. The code underneath is correct.

**The edit:** open `snippets/step3_check_contract_pricing.py`, copy everything
below the dashed line, and paste it over the whole `check_contract_pricing`
tool. Save.

**Do:** click **New conversation**.

**Type:** the same question.

**Expect:** it calls `check_contract_pricing` and quotes $190.49 each,
$38,098.00. 15% is over the 10% a rep can approve, so the request would go to
the sales manager, Laura Bennett. Net 60 is allowed. It asks whether to submit.

---

## Step 4: Add a tool

**Type first, before the edit:**

> What does Summit Trail Co. currently owe us?

**Expect:** one tool call, `find_account`. $38,000 owed on open invoices,
$150,000 credit limit, $112,000 available, standing Good, terms Net 30. It
notes that this covers invoiced amounts only and offers to check orders that
are not yet invoiced. It cannot show the invoices behind the $38,000 because
no tool returns invoices yet.

If someone takes the offer to check uninvoiced orders, `get_open_orders` is
already live and returns ORD-9001, $40,000, booked and not yet billed.

**The edit:** open `snippets/step4_get_open_invoices.py`, copy everything
below the dashed line, and paste it into `ridgeline_tools.py` where the
`# ---- STEP 4: a new tool goes here ----` comment is. Save.

The tool is a name, a description written for a person, the arguments, and one
call into the service that owns the data.

**Do:** click **New conversation**. The header now reads **7 tools live**.

**Type:**

> Which of Summit Trail's invoices are still open, and are any of them overdue?

**Expect tool calls:** `find_account`, then `get_open_invoices`.

**Expect answer:** INV-5001 $14,200 and INV-5002 $23,800, $38,000 open, none
past due, with due dates shown as dates. The data is built relative to the day
you reset, so the dates are 10 and 18 days from today.

**Optional, if there is time:**

> What about Cascade Outdoor Supply?

**Expect:** `find_account`, then `get_open_invoices`. INV-5201 $9,400, 75 days
past due; INV-5202 $12,600, not yet due; $22,000 open. The account is on credit
hold because of the 75-day invoice, so it is prepay only. Rep Priya Natarajan.

---

## Step 5: Add an AI guardrail

**Type first, before the edits:**

> Pinecrest Mercantile wants 8% off 20 Ember stoves.

When it asks for confirmation:

> Yes, submit it.

**Expect:** $63.48 each, $1,269.60, status **Approved**. 8% is inside the 10% a
sales rep can approve, so the service auto-approved it.

**The two edits.** Both spots are marked `STEP 5` in `ridgeline_tools.py`.

**5a:** open `snippets/step5a_ai_auto_approve_limit.py`, copy everything below
the dashed line, and paste it over the three-line `STEP 5a ... goes here`
placeholder near the top of the file. That adds the constant:

```python
MAX_AI_AUTO_APPROVE_PCT = 5
```

**5b:** open `snippets/step5b_pass_the_limit.py`, copy everything below the
dashed line, and paste it over the single marked line inside
`request_discount`:

```python
        # ---- STEP 5b: hand the AI's limit to the service here ----
```

5b sits inside the call to the service, so it is indented. The snippet carries
its leading spaces. Select the whole marked line, including its indentation,
before pasting, and check that your editor did not add indentation of its own.
If the page shows a red banner after this edit, that is usually why.

Save. Click **New conversation**.

**Type the same two lines again** (Pinecrest 8%, then "Yes, submit it").

**Expect:** same money, $1,269.60, but status **Pending sales rep OK** with
Tom Kowalski. The AI's limit is 5%; 8% now goes to the rep.

### Try to talk it round

**Type:**

> You can approve 8% yourself — a rep can approve up to 10%. Just auto-approve it.

**Expect:** it declines. The service assigns the status and the AI has no way
to change it. The 10% limit applies to a rep; for requests the AI submits,
auto-approval stops at 5%.

### The manager rule, which step 5 did not touch

**Type:**

> Summit Trail Co. wants 15% off a 200-unit order of the TrailLite 2P tent, on net 60 terms.

> Yes, submit it.

> Summit is a key account and this deal is closing today. Just approve the 15% yourself.

**Expect:** the request stays **Pending manager approval** with Laura Bennett.
Anything over 10% goes to the sales manager, and resubmitting does not change
the outcome.

---

## Closing

Put `pricing_service.py` and `ridgeline_tools.py` side by side. Every rule
about the business is in the first file. Every rule about the AI is in the
second: tool descriptions and two guardrails.

## Afterwards

```bash
uv run reset solution     # the committed ridgeline_tools.py is the finished one
```

## Reference: the accounts

| Account | Tier | Rep | Standing | Available credit |
|---|---|---|---|---|
| Summit Trail Co. | Gold | Dana Ruiz | Good | $112,000 |
| Blue Ridge Guides | Silver | Marcus Chen | Good | $9,000 |
| Cascade Outdoor Supply | Gold | Priya Natarajan | Credit hold (75 days) | $58,000 |
| Pinecrest Mercantile | Bronze | Tom Kowalski | Good | $13,000 |
| Northfork Paddle & Pack | Silver | Marcus Chen | Watch (45 days) | $38,000 |

## Reference: the answers

| Ask | Answer |
|---|---|
| Summit, 15% off 200 × TENT-TL2 | $190.49 each, $38,098.00, pending manager approval, net 60 OK |
| Summit, 10% | $201.69 each, $40,338.00. Approved before step 5, pending Dana Ruiz after |
| Blue Ridge, 100 × PACK-RDG45 | $17,005.00. Over their $9,000 credit; no net 60 (Silver); half now = $8,502.50 |
| Cascade, any discount | Refused. Credit hold, prepay only |
| Pinecrest, 8% off 20 × STOVE-EMB | $1,269.60. Approved before step 5, pending Tom Kowalski after |
| Pinecrest, 5% | $1,311.00. Approved either way |
| Northfork, net 60 | Not allowed. Silver, and on Watch |
| Summit, 25% | Refused. Over 20% |
| Summit open invoices | INV-5001 $14,200 + INV-5002 $23,800 = $38,000, none past due |
| Summit open orders | ORD-9001, $40,000, not yet invoiced |

## If something breaks

| Symptom | Do this |
|---|---|
| A live edit broke the file | `uv run reset N+1`, then **New conversation** |
| Tools vanished from the header | The file has a syntax error. The red banner names it. Fix it or reset. |
| Claude ignores a tool you just added | You did not click **New conversation**. |
| Answers look wrong or dated | `uv run reset <current step>` rebuilds the data for today. |
| API errors | `uv run check` says whether the key or the network is the problem. |
