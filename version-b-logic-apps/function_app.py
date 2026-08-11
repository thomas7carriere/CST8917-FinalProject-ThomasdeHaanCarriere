import azure.functions as func
import logging
import json

app = func.FunctionApp()

VALID_CATEGORIES = {"travel", "meals", "supplies", "equipment", "software", "other"}
REQUIRED_FIELDS = {"employee_name", "employee_email", "amount", "category", "description", "manager_email"}


@app.route(auth_level=func.AuthLevel.FUNCTION, methods=["POST"])
def validate_expense(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("validate_expense function triggered.")

    try:
        expense = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"valid": False, "reason": "Request body is not valid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    missing = REQUIRED_FIELDS - expense.keys()
    if missing:
        return func.HttpResponse(
            json.dumps({"valid": False, "reason": f"Missing fields: {sorted(missing)}"}),
            status_code=200,
            mimetype="application/json"
        )

    if expense.get("category") not in VALID_CATEGORIES:
        return func.HttpResponse(
            json.dumps({"valid": False, "reason": "Invalid category"}),
            status_code=200,
            mimetype="application/json"
        )

    # Basic type check on amount, since Logic Apps will pass it through as-is
    try:
        float(expense["amount"])
    except (ValueError, TypeError):
        return func.HttpResponse(
            json.dumps({"valid": False, "reason": "Amount must be a number"}),
            status_code=200,
            mimetype="application/json"
        )

    return func.HttpResponse(
        json.dumps({"valid": True, "reason": ""}),
        status_code=200,
        mimetype="application/json"
    )