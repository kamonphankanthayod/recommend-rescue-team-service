# API Contract #1: Get Rescue Teams

import os
import json
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])

GSI_NAME = "team_status-index"

def decimal_to_number(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError

def format_team(item):
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


def get_available_teams(event):
    trace_id = event["requestContext"]["requestId"]

    print(f"[{trace_id}] START --- GET /v1/teams")

    try:
        params = event.get("queryStringParameters") or {}

        status_param = params.get("status", "AVAILABLE")
        capability = params.get("capability")

        # parse status
        if status_param.upper() == "ALL":
            statuses = ["AVAILABLE", "BUSY", "OFFLINE"]
        else:
            statuses = [s.strip().upper() for s in status_param.split(",")]

        VALID_STATUS = {"AVAILABLE", "BUSY", "OFFLINE"}

        for s in statuses:
            if s not in VALID_STATUS:
                return format_error_response(
                    400,
                    "VALIDATION_ERROR",
                    f"Invalid status: {s} - valid status: {VALID_STATUS}",
                    trace_id
                )

        print(f"[{trace_id}] Querying statuses: {statuses}")

        items = []

        for status in statuses:
            response = table.query(
                IndexName=GSI_NAME,
                KeyConditionExpression=Key("team_status").eq(status)
            )
            items.extend(response.get("Items", []))

        print(f"[{trace_id}] Found {len(items)} teams before filtering")

        # filter capability
        if capability:
            items = [
                t for t in items
                if capability in t.get("capabilities", [])
            ]
            print(f"[{trace_id}] After capability filter: {len(items)} teams")

        teams = [format_team(t) for t in items]

        print(f"[{trace_id}] 200 SUCCESS - Returning {len(teams)} teams")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(
                {
                    "teams": teams,
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
            "Fail to Get Teams",
            trace_id
        )