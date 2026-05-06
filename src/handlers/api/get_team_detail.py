# API Contract #2: Get Rescue Team Detail

import os
import json
from decimal import Decimal

import boto3

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])


def decimal_to_number(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError


def format_team_detail(item):
    return {
        "team_id": item["team_id"],
        "team_name": item["team_name"],
        "team_type": item["team_type"],
        "team_status": item["team_status"],
        "capabilities": item.get("capabilities", []),
        "specialties": item.get("specialties", []),
        "current_location": item.get("current_location"),
        "equipment": item.get("equipment", []),
        "capacity": item.get("capacity"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at")
    }


def get_team_detail(event):
    trace_id = event["requestContext"]["requestId"]

    path_params = event.get("pathParameters") or {}
    team_id = path_params.get("team_id")

    print(f"[{trace_id}] START --- GET /v1/teams/{team_id}")

    try:
        # Validation: missing
        if not team_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - team_id is required")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "team_id is required",
                trace_id,
                [{"field": "team_id", "issue": "missing"}]
            )

        # Validation: format (basic)
        if not team_id.startswith("TEAM-"):
            print(f"[{trace_id}] 400 VALIDATION_ERROR - invalid format")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "team_id must be a valid String",
                trace_id,
                [{"field": "team_id", "issue": "invalid_format"}]
            )

        # Get item from DynamoDB
        response = table.get_item(
            Key={"team_id": team_id}
        )

        item = response.get("Item")

        # Not found
        if not item:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - {team_id}")

            return format_error_response(
                404,
                "REFERENCE_NOT_FOUND",
                "team_id not found",
                trace_id
            )

        # Format response
        result = format_team_detail(item)

        print(f"[{trace_id}] 200 SUCCESS - Found team {team_id}")
        # print(f"[{trace_id}] Data: {json.dumps(result, default=decimal_to_number)}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(
                {
                    **result,
                    "trace_id": trace_id
                },
                default=decimal_to_number
            )
        }

    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to get rescue team detail",
            trace_id
        )