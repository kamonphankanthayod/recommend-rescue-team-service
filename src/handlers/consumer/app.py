import json

from handlers.consumer.generate_recommendation import generate_recommendation
from shared.utils.validator import is_valid_uuid


class ValidationError(Exception):
    pass


# -------------------------
# Validation Function
# -------------------------
def validate_message(header, body):
    # Header
    if not header:
        raise ValidationError("Missing header")

    if header.get("messageType") != "RescueRequestEvaluateEvent":
        raise ValidationError("Invalid messageType")

    if not is_valid_uuid(header.get("traceId")):
        raise ValidationError("Invalid traceId")

    if not is_valid_uuid(header.get("correlationId")):
        raise ValidationError("Invalid correlationId")

    # Body
    ## Body required fields
    required_fields = [
        "requestId",
        "incidentId",
        "evaluateId",
        "requestType",
        "incidentType",
        "peopleCount",
        "location"
    ]

    for f in required_fields:
        if body.get(f) is None:
            raise ValidationError(f"Missing field: {f}")

    ## UUID validation
    if not is_valid_uuid(body["requestId"]):
        raise ValidationError("Invalid requestId")

    if not is_valid_uuid(body["incidentId"]):
        raise ValidationError("Invalid incidentId")

    if not is_valid_uuid(body["evaluateId"]):
        raise ValidationError("Invalid evaluateId")

    ## priorityLevel
    valid_levels = {"LOW", "NORMAL", "HIGH", "CRITICAL"}
    if body.get("priorityLevel") not in valid_levels:
        raise ValidationError("Invalid priorityLevel")

    ## peopleCount
    if not isinstance(body["peopleCount"], (int, float)) or body["peopleCount"] < 0:
        raise ValidationError("Invalid peopleCount")

    ## location
    loc = body["location"]
    lat = loc.get("latitude")
    lng = loc.get("longitude")

    if lat is None or lng is None:
        raise ValidationError("Missing latitude/longitude")

    if not (-90 <= lat <= 90):
        raise ValidationError("Latitude out of range")

    if not (-180 <= lng <= 180):
        raise ValidationError("Longitude out of range")


# -------------------------
# Lambda Handler
# -------------------------
def lambda_handler(event, context):
    # print("RAW EVENT:", json.dumps(event))
    print("START - recommendation-event-consumer - v1")

    for record in event.get("Records", []):
        try:
            # 1. Parse SQS
            sqs_body = json.loads(record["body"])

            # 2. Parse SNS
            if "Message" in sqs_body:
                message = sqs_body["Message"]
                sns_message = json.loads(message) if isinstance(message, str) else message
            else:
                sns_message = sqs_body

            print("SNS MESSAGE:", json.dumps(sns_message))

            header = sns_message.get("header", {})
            body = sns_message.get("body", {})

            trace_id = header.get("traceId", "unknown-trace")

            print(f"[{trace_id}] Received message")

            # 3. Validate
            validate_message(header, body)

            # 4. Call business logic
            generate_recommendation(sns_message)

            print(f"[{trace_id}] SUCCESS - handler/consumer/app.py")

        except ValidationError as e:
            print(f"[VALIDATION ERROR] {str(e)}")
            continue  # ไม่ retry

        except Exception as e:
            print(f"[ERROR] {str(e)}")
            raise e  # retry โดย SQS

    return {"statusCode": 200}