import azure.functions as func
import azure.durable_functions as df
import logging
from datetime import timedelta

myApp = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}
REQUIRED_FIELDS = {"employee_name", "employee_email", "amount", "category", "description", "manager_email"}

# ---- Client function ----
@myApp.route(route="expenses")
@myApp.durable_client_input(client_name="client")
async def http_start(req: func.HttpRequest, client):
    payload = req.get_json()
    instance_id = await client.start_new("expense_orchestrator", client_input=payload)
    logging.info(f"Started orchestration with ID = '{instance_id}'.")
    return client.create_check_status_response(req, instance_id)

# ---- Orchestrator ----
@myApp.orchestration_trigger(context_name="context")
def expense_orchestrator(context: df.DurableOrchestrationContext):
    expense = context.get_input()

    is_valid = yield context.call_activity("validate_expense", expense)
    if not is_valid["valid"]:
        yield context.call_activity("send_notification", {
            "expense": expense, "outcome": "rejected", "reason": is_valid["reason"]
        })
        return {"status": "validation_error", "reason": is_valid["reason"]}

    if expense["amount"] < 100:
        yield context.call_activity("process_auto_approval", expense)
        yield context.call_activity("send_notification", {"expense": expense, "outcome": "approved"})
        return {"status": "approved", "auto": True}

    # Manager approval path
    timeout_deadline = context.current_utc_datetime + timedelta(seconds=20)  # adjust for testing
    timer_task = context.create_timer(timeout_deadline)
    approval_event = context.wait_for_external_event("ManagerDecision")

    winner = yield context.task_any([approval_event, timer_task])

    if winner == approval_event:
        timer_task.cancel()
        decision = approval_event.result
        if isinstance(decision, str):
            import json
            decision = json.loads(decision)
        outcome = decision["decision"]
    else:
        outcome = "escalated"

    yield context.call_activity("send_notification", {"expense": expense, "outcome": outcome})
    return {"status": outcome}


# ---- Activities ----
@myApp.activity_trigger(input_name="expense")
def validate_expense(expense: dict):
    missing = REQUIRED_FIELDS - expense.keys()
    if missing:
        return {"valid": False, "reason": f"Missing fields: {missing}"}
    if expense["category"] not in VALID_CATEGORIES:
        return {"valid": False, "reason": "Invalid category"}
    return {"valid": True}

@myApp.activity_trigger(input_name="expense")
def process_auto_approval(expense: dict):
    logging.info(f"Auto-approved: {expense['employee_name']}")
    return {"processed": True}

@myApp.activity_trigger(input_name="payload")
def send_notification(payload: dict):
    email = payload['expense'].get('employee_email', 'unknown recipient')
    logging.info(f"Notify {email}: outcome = {payload['outcome']}")
    return {"sent": True}

# ---- Manager decision endpoint ----
@myApp.route(route="expenses/{instance_id}/decision", methods=["POST"])
@myApp.durable_client_input(client_name="client")
async def manager_decision(req: func.HttpRequest, client):
    instance_id = req.route_params.get("instance_id")
    body = req.get_json()  # {"decision": "approved"} or {"decision": "rejected"}
    await client.raise_event(instance_id, "ManagerDecision", body)
    return func.HttpResponse(status_code=200)