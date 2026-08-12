# CST8917-FinalProject-ThomasdeHaanCarriere

- Name: Thomas de Haan Carriere
- Student #: 41276876
- Course: CST8917 Serverless Applications
- Project: Assignment 2 / Final Project
- Date: 2026/08/11

## Version A (Durable Functions)
### Summary: 
Version A is a Python Azure Functions app implementing the expense reporting workflow with durable orchestration. An HTTP-triggered client function starts the orchestration and returns the standard status-polling URLs. The orchestrator calls the validate_expense activity, then branches on amount requested: expenses under $100 go through process_auto_approval; expenses at or above $100 race a durable timer against context.wait_for_external_event("ManagerDecision") using context.task_any(...). A separate HTTP endpoint (manager_decision) raises that event by instance ID. A final send_notification activity logs the outcome. No e-mail is actually sent for Version A.

### Design:

- task_any([timer_task, approval_event]) was used specifically because it is the platform's native mechanism for racing a timeout against a human decision

### Challenges:

- The timeout was deliberately shortened during testing (20 seconds) which made it difficult to test under the time constraints, without having to wait too long for the escalation to occur.

- The final notification step logs the outcome rather than sending a real email. I attempted to add real SMTP delivery through the same Outlook account, but the tenant doesn't allow an app-password option with 2FA.

## Version B (Logic App) 
### Summary: 
Version B is a Consumption-tier Logic App  triggered by a Service Bus queue. It parses the incoming message, calls a separately deployed Python validation Azure Function over plain HTTP, and branches based on the validity of the request and amount requested using nested Condition actions. Expenses under $100 send an "approved" message directly to a Service Bus topic (expense-outcomes). Expenses at or above $100 write a "pending" row to an Azure Table Storage table, email the manager via the Office 365 Outlook connector, and then wait. Logic Apps Consumption has no built-in "wait for an external event" action, this wait is a Do/Until loop polling that row every 20 seconds (test setting) up to a Count/Timeout limit, chosen over setting up a second Logic App just to receive a callback. If the row is still "pending" when the limit is hit, the workflow escalates.

### Design:


### Challenges:

- The Azure Portal's Function App creation blade does not offer Python as a runtime stack until the OS was explicitly switched to Linux.

- The portal's Run History view kept showing runs as "in progress" for several minutes after the Azure REST API (and the portal itself) confirmed they had already Succeeded

## Comparison Analysis

### Development Experience

Version A was faster to build and much easier to debug. Because it is plain Python, every failure produced a real traceback pointing at a specific line. Every bug encountered in Version A was a logic-level bug with an unambiguous fix. Version B was built through a visual designer that repeatedly disagreed with its own underlying JSON: an expression that displayed correctly in the Parameters panel was, on at least one occasion, not actually persisted underneath, and the only way to confirm or fix that was to inspect and hand-edit Code view directly. I came away with far more confidence that Version A's logic was correct, because we could reason about it as ordinary code; with Version B, confidence came only after cross-checking the portal's own state against the REST API, because the portal itself proved to be an unreliable indicator of what had actually run.

### Testability

Version A can be tested and iterated on entirely locally, using func start against the Azurite storage emulator, with no Azure resources required until deployment. Because the orchestrator is a plain Python generator function operating on activities that are plain functions, it is straightforward to unit-test validate_expense or process_auto_approval in isolation with pytest, and the orchestrator's branching logic could be tested by mocking context.call_activity. Version B has no true local execution story for a Consumption Logic App, every test run in this project used live Azure resources. There is no meaningful way to write an automated unit test against a Consumption workflow definition; the closest available options are integration-style tests driving the Service Bus queue and polling Run History via the REST API, which is exactly the workaround I ended up using manually. Version A is easier to test, at every level.

### Error Handling

Durable Functions gives full programmatic control over retries and recovery: activities can be called with an explicit RetryOptions (max attempts, backoff), and because the orchestrator is deterministic code, any exception can be caught with an ordinary Python try/except and routed to custom compensation logic. We used this implicitly by choosing .get() with defaults rather than letting a missing field crash an activity. Logic Apps also supports retry policies on individual actions (configurable count/interval), but recovery logic has to be expressed as more actions and conditions on the canvas rather than a language construct, which is workable but noticeably more effort for anything beyond a simple retry — our validation-error path, for instance, needed an explicit .get()-equivalent field-existence check built as parts of the JSON body construction rather than a single defensive line of code.

### Human Interaction Pattern

This was the sharpest difference in the project. Durable Functions' Task.any([timer_task, approval_event]) is a first-class SDK primitive built exactly for "wait for a human or a timeout", it directly returns which of the two happened, with no interpretation needed. Logic Apps Consumption has no equivalent action, so we hand-built the same behavior from a Do/Until loop polling an Azure Table Storage row, with a Count/Timeout limit standing in for the timeout. Critically, an Until loop only ever returns a value, not a reason. Determining whether the loop exited because the manager responded or because it gave up required a second, separately-built nested Condition after the loop. Version A's approach is unambiguously more natural for this pattern. Version B's is a legitimate, documented workaround, but a workaround nonetheless.

### Observability

Version A's statusQueryGetUri returns a single JSON object with an explicit runtimeStatus and structured output, which was reliable and easy to reason about throughout testing, combined with plain terminal logs. Version B's Run History repeatedly showed stale state during this project - runs displayed as "in progress" well after Azure's own REST API confirmed they had Succeeded minutes earlier, which cost real debugging time until we started cross-checking with az rest. Once past that quirk, the visual run trace (a graph of which branch executed, with inputs/outputs per action) is genuinely useful for a non-developer trying to understand what happened - an advantage Version A's log-based approach doesn't offer. Observability is roughly a wash in capability, but Version A was more trustworthy in practice.

### Cost

Estimated using Azure's published Consumption/Standard-tier rate sheets (East US, pay-as-you-go, as of August 2026 - the same rates the Azure Pricing Calculator draws from), at two volumes. Assumptions are stated inline since actual bills depend heavily on message size, average duration, and connector mix.

Version A (Durable Functions): Assuming ~7 billable function executions per expense (client trigger, orchestrator replays, activities) averaging ~0.128 GB at ~200 ms each (~0.18 GB-s/expense), plus negligible Azure Storage transaction costs for orchestration history:

100/day (≈3,000/month): well inside the Consumption plan's free monthly grant (1M executions, 400,000 GB-s) → ≈$0–1/month.
10,000/day (≈300,000/month, ≈2.1M executions, ≈54,000 GB-s): still inside the GB-s free grant; ≈1.1M executions billed past the free 1M at $0.20/million → ≈$1–3/month.

Version B (Logic Apps + Service Bus): Assuming ~15 actions per processed expense (a blend of built-in actions at $0.000025 and Standard-connector calls — Service Bus, Table Storage, Outlook — at $0.000125), plus a fixed polling-trigger cost (independent of message volume: a 3-minute recurrence trigger fires ≈14,400 times/month regardless of whether a message is present), plus the Service Bus Standard tier's flat $10/month base charge (which covers up to 12.5M operations, so usage-based Service Bus charges stay at $0 at both volumes tested):

100/day (≈3,000/month): ≈$2.50 (actions) + ≈$0.36 (polling) + $10 (Service Bus base) → ≈$13/month.
10,000/day (≈300,000/month): ≈$247.50 (actions) + ≈$0.36 (polling) + $10 (Service Bus base) → ≈$258/month.

## Recomendation

If I were building this for real, I'd go with Durable Functions. Waiting for a manager's decision or a timeout is something the platform handles natively (task_any), while Logic Apps needed a polling loop I had to build myself to do the same thing. Durable Functions was also way cheaper at scale in my estimates - about $1-3/month versus $13-258/month - and easier to test and debug since it's just Python with real error messages, not a designer that sometimes didn't save what I clicked.

Logic Apps makes more sense when the workflow is mostly about connecting services together rather than complex logic, or when the people maintaining it aren't developers. The visual canvas is easier to read at a glance, even with the friction it caused during this project.

So: Durable Functions for correctness and cost, Logic Apps for integration-heavy work non-developers need to read or maintain.

## References

- Microsoft. "Pricing – Azure Functions." Azure. https://azure.microsoft.com/en-us/pricing/details/functions/
- Microsoft. "Usage metering, billing, and pricing – Azure Logic Apps." Microsoft Learn. https://learn.microsoft.com/en-us/azure/logic-apps/logic-apps-pricing
- Microsoft. "Pricing – Service Bus." Azure. https://azure.microsoft.com/en-us/pricing/details/service-bus/
- Microsoft. "Durable Functions overview – Azure Functions." Microsoft Learn. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview

## AI Disclosure

AI was used to help generate the Azure Functions in both Version A & B, as well as troubleshooting the logic app. It was also used to help validate my compairason analysis and help calculate costs based on Azure's pricing calculator.