# utils/auth.py

def authorize_dispatcher(event):
    """
    ตรวจสอบ Authorization Header ว่ามี Token ที่ถูกต้องและมีสิทธิ์ (Role) เป็น Dispatcher หรือไม่
    Returns: (is_authorized: bool, error_message: str)
    """
    # ดึง headers ออกมา (API Gateway มักจะแปลง key เป็นตัวเล็กทั้งหมด)
    headers = event.get("headers", {})
    auth_header = headers.get("authorization", "")

    # 1. ตรวจสอบรูปแบบ Header ต้องเป็น "Bearer <token>"
    if not auth_header or not auth_header.startswith("Bearer "):
        return False, "Missing or invalid Authorization header format. Expected 'Bearer <token>'"

    # 2. สกัดเอาเฉพาะ Token
    token = auth_header.split(" ")[1]

    # -------------------------------------------------------------
    # 3. MOCK VALIDATION: จุดนี้คือที่ที่จะเอา Token ไป Verify
    # ในระบบจริง อาจจะใช้ jwt.decode(token, SECRET_KEY) เพื่อดู Payload
    # และเช็คว่า payload.get("role") == "DISPATCHER" หรือไม่
    # -------------------------------------------------------------
    
    # สมมติว่า Token ที่ถูกต้องสำหรับ Dispatcher คือ "mock-dispatcher-token-123"
    valid_tokens = [
        "mock-dispatcher-token-123",  # Token สำหรับ Dispatcher
        "mock-system-token-999"       # Token สำหรับ Manage Dispatch Service
    ]

    if token in valid_tokens:
        return True, ""
    else:
        return False, "Invalid token or insufficient permissions"