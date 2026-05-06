# API Contract #3: Create Rescue Teams

import os
import json
import uuid
from datetime import datetime
from decimal import Decimal

import boto3

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])


def create_team(event):
    trace_id = event["requestContext"]["requestId"]

    print(f"[{trace_id}] START --- POST /v1/teams")

    try:
        body = json.loads(event.get("body", "{}"))

        team_name = body.get("team_name")
        team_type = body.get("team_type")
        capabilities = body.get("capabilities")
        current_location = body.get("current_location")
        capacity = body.get("capacity")

        # Validation
        if not team_name:
            return format_error_response(
                400, "VALIDATION_ERROR", "team_name is required", trace_id
            )

        if not team_type:
            return format_error_response(
                400, "VALIDATION_ERROR", "team_type is required", trace_id
            )

        if not capabilities:
            return format_error_response(
                400, "VALIDATION_ERROR", "capabilities is required", trace_id
            )

        if not current_location:
            return format_error_response(
                400, "VALIDATION_ERROR", "current_location is required", trace_id
            )

        if capacity is None:
            return format_error_response(
                400, "VALIDATION_ERROR", "capacity is required", trace_id
            )

        # Generate ID
        team_id = f"TEAM-{uuid.uuid4().hex[:6]}"
        now = datetime.utcnow().isoformat(timespec='milliseconds') + "Z"

        item = {
            "team_id": team_id,
            "team_name": team_name,
            "team_type": team_type,
            "team_status": "AVAILABLE",
            "capabilities": capabilities,
            "specialties": body.get("specialties", []),  
            "current_location": {
                "lat": float(current_location.get("lat")),
                "lng": float(current_location.get("lng"))
            },
            "equipment": body.get("equipment", []),
            "capacity": capacity,
            "created_at": now,
            "updated_at": now
        }
        # แปลง float -> Decimal (DynamoDB requirement)
        item_p = json.loads(json.dumps(item), parse_float=Decimal)

        table.put_item(Item=item_p)

        print(f"[{trace_id}] Rescue Team created: {team_id}")

        return {
            "statusCode": 201,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "team_id": team_id,
                "status": "AVAILABLE",
                "created_at": now,
                "trace_id": trace_id
            })
        }

    except Exception as e:
        print(f"[{trace_id}] ERROR: {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to create rescue team",
            trace_id
        )