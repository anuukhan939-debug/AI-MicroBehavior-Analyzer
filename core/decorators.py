from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def role_required(allowed_roles):
    """Decorator to check if user has required role"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('core:login')
            
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('core:dashboard')
        return wrapper
    return decorator

def session_required():
    """Decorator to check if user has an active session"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if hasattr(request, 'session') and request.session.get('active_session_id'):
                return view_func(request, *args, **kwargs)
            else:
                messages.warning(request, 'Please start a session first.')
                return redirect('core:start_session')
        return wrapper
    return decorator