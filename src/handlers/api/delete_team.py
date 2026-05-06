# API Contract #4: Delete Rescue Team

import os
import boto3
from botocore.exceptions import ClientError

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])


def delete_team(event):
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
        parts = raw_path.strip("/").split("/") # จะได้ ['v1', 'teams', 'TEAM-902919']
        
        # ตรวจสอบว่า path ถูกต้องและมีตำแหน่งของ team_id
        if len(parts) >= 3 and parts[-2] == "teams":
            team_id = parts[-1]

    print(f"[{trace_id}] START --- DELETE /v1/teams/{team_id}")

    try:
        # -------------------------
        # 1. Validate team_id
        # -------------------------
        if not team_id:
            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "team_id is required",
                trace_id,
                [{"field": "team_id", "issue": "missing"}]
            )

        if not team_id.startswith("TEAM-"):
            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "Invalid team_id format",
                trace_id,
                [{"field": "team_id", "issue": "invalid_format"}]
            )

        # -------------------------
        # 2. Idempotent delete (safe)
        # -------------------------
        try:
            table.delete_item(
                Key={"team_id": team_id},
                ConditionExpression="attribute_exists(team_id)"  # กันลบของที่ไม่มี
            )

            print(f"[{trace_id}] Deleted team: {team_id}")

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # ไม่เจอ item -> ถือว่า delete สำเร็จแบบ idempotent
                print(f"[{trace_id}] Team not found (already deleted): {team_id}")
            else:
                print(f"[{trace_id}] DynamoDB error: {str(e)}")
                raise

        # -------------------------
        # 3. Return 204
        # -------------------------
        return {
            "statusCode": 204,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }

    except Exception as e:
        print(f"[{trace_id}] ERROR: {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Failed to delete rescue team",
            trace_id
        )