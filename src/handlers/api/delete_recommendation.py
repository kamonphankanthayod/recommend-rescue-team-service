# API Contract #8: Delete Recommendation

import os

import boto3
from botocore.exceptions import ClientError

from shared.utils.error_response import format_error_response
from shared.utils.validator import is_valid_uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["REC_TABLE_NAME"])


def delete_recommendation(event):
    # HttpApi แบบ $default จะซ่อน requestId ไว้ใน requestContext
    req_context = event.get("requestContext", {})
    trace_id = req_context.get("requestId", "UNKNOWN_TRACE_ID")
    
    # -------------------------------------------------------------
    # การดึง recommendation_id รองรับทั้งแบบระบุ Path และแบบ $default
    # -------------------------------------------------------------
    recommendation_id = None
    path_params = event.get("pathParameters")
    
    if path_params and "recommendation_id" in path_params:
        # กรณีตั้งค่า Route แบบระบุตัวแปรใน API Gateway
        recommendation_id = path_params["recommendation_id"]
    else:
        # กรณีใช้ $default Route ให้ตัดคำจาก rawPath แทน
        raw_path = event.get("rawPath", "") # เช่น "/v1/recommendations/219d078a-5c63-4387-a3bf-6f61e2c9c6aa"
        parts = raw_path.strip("/").split("/") # จะได้ ['v1', 'recommendations', '219d078a-5c63-4387-a3bf-6f61e2c9c6aa']
        
        # ตรวจสอบว่า path ถูกต้องและมีตำแหน่งของ recommendation_id
        if len(parts) >= 4 and parts[-2] == "recommendations":
            recommendation_id = parts[-1]

    print(f"[{trace_id}] START --- DELETE /v1/recommendations/{recommendation_id}")

    try:
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

        response = table.delete_item(
            Key={"recommendation_id": recommendation_id},
            ReturnValues="ALL_OLD"
        )

        deleted_item = response.get("Attributes")

        if deleted_item:
            print(f"[{trace_id}] Item existed and deleted")
        else:
            print(f"[{trace_id}] Item did not exist (idempotent delete)")

        print(f"[{trace_id}] 204 No Content - Recommendation deleted")

        return {
            "statusCode": 204,
            "body": ""
        }

    except ClientError as e:
        print(f"[{trace_id}] 500 DYNAMODB_ERROR - {str(e)}")

        return format_error_response(
            500,
            "DATABASE_ERROR",
            "Failed to delete recommendation",
            trace_id
        )

    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Unexpected error occurred",
            trace_id
        )