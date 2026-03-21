# PATCH method for update recommendation

import os
import json
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from utils.error_response import format_error_response
from utils.validator import is_valid_uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["TABLE_NAME"])    #TABLE_NAME = "recommendations"

ALLOWED_UPDATE_STATUSES = ["ACCEPTED", "REJECTED"]

def update_recommendation_status(event):
    trace_id = event["requestContext"]["requestId"]
    recommendation_id = event.get("pathParameters", {}).get("recommendation_id")
    
    print(f"[{trace_id}] START --- PATCH /v1/recommendations/{recommendation_id}/status")

    try:
        # 1. Validation Path Parameter
        ## Validation Error: 400 Bad Request
        if not recommendation_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - recommendation_id is required")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "recommendation_id is required",
                trace_id,
                [{"field": "recommendation_id", "issue": "missing"}]
            )
        
        ## Validation Error: 400 Bad Request
        if not is_valid_uuid(recommendation_id):
            print(f"[{trace_id}] 400 VALIDATION_ERROR - invalid UUID format")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "recommendation_id must be a valid UUID",
                trace_id,
                [{"field": "recommendation_id", "issue": "invalid_format"}]
            )

        # 2. Parse & Validate Body
        body = json.loads(event.get("body", "{}"))
        new_status = body.get("recommendation_status")
        # print(f"[{trace_id}] new_status: {new_status} and ALLOWED_UPDATE_STATUSES: {ALLOWED_UPDATE_STATUSES}")
        selected_team_id = body.get("selected_team_id")
        reason = body.get("reason", "")

        if new_status not in ALLOWED_UPDATE_STATUSES:
            return format_error_response(
                400,
                "VALIDATION_ERROR",
                f"status must be one of {ALLOWED_UPDATE_STATUSES}",
                trace_id
            )
            
        if new_status == "ACCEPTED" and not selected_team_id:
            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "selected_team_id is required when status is ACCEPTED",
                trace_id
            )

        # 3. เตรียมคำสั่ง Update DynamoDB
        updated_at = datetime.utcnow().isoformat(timespec='milliseconds') + "Z"

        print(f"[{trace_id}] Updating recommendation {recommendation_id} to status {new_status}")
        
        update_expr = "SET recommendation_status = :ns, updated_at = :ua"
        expr_attrs = {
            ':ns': new_status,
            ':ua': updated_at,
            ':expected_status': 'GENERATED' # Condition: ต้องเป็น GENERATED อยู่เท่านั้น
        }
        
        if selected_team_id:
            update_expr += ", selected_team_id = :tid"
            expr_attrs[':tid'] = selected_team_id
            
        if reason:
            update_expr += ", status_reason = :rsn"
            expr_attrs[':rsn'] = reason

        # 4. สั่ง Update พร้อมแนบ Condition
        response = table.update_item(
            Key={'recommendation_id': recommendation_id},
            UpdateExpression=update_expr,
            ConditionExpression="recommendation_status = :expected_status",
            ExpressionAttributeValues=expr_attrs,
            ReturnValues="ALL_NEW" # ขอข้อมูลที่อัปเดตแล้วกลับมาด้วย
        )
        
        updated_item = response.get("Attributes", {})
        
        print(f"[{trace_id}] 200 OK - Successfully updated status to {new_status}")
        
        # คืนค่ากลับไป (อาจจะใช้ format_get_recommendation มาช่วยจัดฟอร์แมตตรงนี้ได้)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "recommendation_id": updated_item.get("recommendation_id"),
                "recommendation_status": updated_item.get("recommendation_status"),
                "selected_team_id": updated_item.get("selected_team_id"),
                "updated_at": updated_item.get("updated_at")
            })
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        # ดัก Error กรณีที่ ConditionExpression ไม่เป็นจริง (เช่น สถานะไม่ใช่ GENERATED)
        if error_code == 'ConditionalCheckFailedException':
            print(f"[{trace_id}] 409 CONFLICT - Cannot update status from current state")
            return format_error_response(
                409, "STATE_CONFLICT", 
                "Recommendation must be in GENERATED status to be updated", trace_id
            )
        print(f"[{trace_id}] 500 DYNAMODB_ERROR - {str(e)}")
        return format_error_response(500, "DATABASE_ERROR", "Failed to update recommendation", trace_id)

    except json.JSONDecodeError:
        return format_error_response(400, "VALIDATION_ERROR", "Invalid JSON body", trace_id)
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - {str(e)}")
        return format_error_response(500, "INTERNAL_SERVER_ERROR", "Unexpected error occurred", trace_id)