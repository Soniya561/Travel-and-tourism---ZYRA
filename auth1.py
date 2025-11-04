# documents/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True
        return obj.owner_id == getattr(request.user, "id", None)

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
