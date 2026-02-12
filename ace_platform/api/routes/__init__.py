"""API route modules for ACE Platform.

This package contains FastAPI routers for different resource types:
- auth: User authentication (login, register, token refresh)
- billing: Billing and subscription management
- oauth: OAuth authentication (Google, GitHub)
- playbooks: Playbook CRUD operations
- usage: Usage reporting for billing dashboard
- evolutions: Evolution statistics and activity
"""

from .account import router as account_router
from .auth import router as auth_router
from .billing import router as billing_router
from .evolutions import router as evolutions_router
from .oauth import router as oauth_router
from .playbooks import router as playbooks_router
from .support import router as support_router
from .usage import router as usage_router

__all__ = [
    "account_router",
    "auth_router",
    "billing_router",
    "evolutions_router",
    "oauth_router",
    "playbooks_router",
    "support_router",
    "usage_router",
]
