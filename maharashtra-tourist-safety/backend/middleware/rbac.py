from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status

from middleware.auth import get_current_user
from db.mongo import get_db


def require_role(*roles: str):
    """
    Dependency factory that enforces RBAC.
    Raises HTTP 403 and writes an audit_log entry when the user's role
    is not in the allowed set.
    """

    async def _check(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            # Log the denied access attempt to audit_log (Req 9.5)
            try:
                db = get_db()
                db["audit_log"].insert_one(
                    {
                        "userId": user["userId"],
                        "action": "ACCESS_DENIED",
                        "resource": "rbac_check",
                        "requiredRoles": list(roles),
                        "userRole": user["role"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "allowed": False,
                    }
                )
            except Exception:
                # Never let audit logging failure block the denial response
                pass

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(roles)}",
            )
        return user

    return _check
