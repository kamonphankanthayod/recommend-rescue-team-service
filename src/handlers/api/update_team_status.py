# API Contract #5: Update Team Status

import os
import json
from datetime import datetime

import boto3

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])

VALID_STATUS = ["AVAILABLE", "BUSY", "OFFLINE"]


def update_team_status(event):
    print(f"Received event: {json.dumps(event)}")
    # HttpApi แบบ $default จะซ่อน requestId ไว้ใน requestContext
    req_context = event.get("requestContext", {})
    trace_id = req_context.get("requestId", "UNKNOWN_TRACE_ID")
    
    # -------------------------------------------------------------
    # การดึง team_id รองรับทั้งแบบระบุ Path และแบบ $default
    # -------------------------------------------------------------
    team_id = None
    path_params = event.get("pathParameters")
    
    if path_params and "team_id" in path_params:
        # กรณีตั้งค่า Route แบบระบุตัวแปรใน API Gateway
        team_id = path_params["team_id"]
    else:
        # กรณีใช้ $default Route ให้ตัดคำจาก rawPath แทน
        raw_path = event.get("rawPath", "") # เช่น "/v1/teams/TEAM-902919"
        parts = raw_path.strip("/").split("/") # จะได้ ['v1', 'teams', 'TEAM-902919', 'status']
        
        # ตรวจสอบว่า path ถูกต้องและมีตำแหน่งของ team_id
        if len(parts) >= 4 and parts[-3] == "teams":
            team_id = parts[-2]

    print(f"[{trace_id}] START --- PATCH /v1/teams/{team_id}/status")

    try:
        # -------------------------
        # Validation: team_id missing
        # -------------------------
        if not team_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - team_id missing")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "team_id is required",
                trace_id,
                [{"field": "team_id", "issue": "missing"}]
            )

        # -------------------------
        # Validation: team_id format
        # -------------------------
        if not team_id.startswith("TEAM-"):
            print(f"[{trace_id}] 400 VALIDATION_ERROR - invalid team_id format")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "team_id must be a valid String",
                trace_id,
                [{"field": "team_id", "issue": "invalid_format"}]
            )

        # -------------------------
        # Parse body
        # -------------------------
        try:
            body = json.loads(event.get("body") or "{}")
        except:
            body = {}

        new_status = body.get("team_status") or body.get("status")
        print(f"[{trace_id}] Parsed new_status: {new_status}")

        # -------------------------
        # Validation: status
        # -------------------------
        if not new_status or new_status not in VALID_STATUS:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - invalid status")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "status must be one of AVAILABLE, BUSY, OFFLINE",
                trace_id
            )

        # -------------------------
        # Check existence
        # -------------------------
        response = table.get_item(
            Key={"team_id": team_id}
        )

        item = response.get("Item")

        if not item:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - {team_id}")

            return format_error_response(
                404,
                "REFERENCE_NOT_FOUND",
                "team_id not found",
                trace_id
            )

        # -------------------------
        # Idempotent update
        # -------------------------
        if item.get("team_status") == new_status:
            print(f"[{trace_id}] No-op (same status)")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "team_id": team_id,
                    "status": new_status,
                    "message": "No change (idempotent)",
                    "trace_id": trace_id
                })
            }

        # -------------------------
        # Update status
        # -------------------------
        updated_at = datetime.utcnow().isoformat(timespec='milliseconds') + "Z"

        table.update_item(
            Key={"team_id": team_id},
            UpdateExpression="SET team_status = :s, updated_at = :u",
            ExpressionAttributeValues={
                ":s": new_status,
                ":u": updated_at
            }
        )

        print(f"[{trace_id}] 200 SUCCESS - Updated {team_id} to {new_status}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "team_id": team_id,
                "status": new_status,
                "updated_at": updated_at,
                "trace_id": trace_id
            })
        }

    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to update rescue team status",
            trace_id
        )