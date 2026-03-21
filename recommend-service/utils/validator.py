import uuid

def is_valid_uuid(val):
    try:
        uuid.UUID(val)
        return True
    except:
        return False