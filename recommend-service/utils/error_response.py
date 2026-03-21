import json

def format_error_response(status_code, code, message, trace_id, details=None):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "error": {
                "code": code,
                "message": message,
                "trace_id": trace_id,
                "details": details or []
            }
        })
    }