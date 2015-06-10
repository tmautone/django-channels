import types
from django.apps import apps


def auto_import_consumers():
    """
    Auto-import consumers modules in apps
    """
    for app_config in apps.get_app_configs():
        for submodule in ["consumers", "views"]:
            module_name = "%s.%s" % (app_config.name, submodule)
            try:
                __import__(module_name)
            except ImportError as e:
                if "no module named %s" % submodule not in str(e).lower():
                    raise


def name_that_thing(thing):
    """
    Returns either the function/class path or just the object's repr
    """
    if hasattr(thing, "__name__"):
        if hasattr(thing, "__class__") and not isinstance(thing, types.FunctionType):
            if thing.__class__ is not type:
                return name_that_thing(thing.__class__)
        if hasattr(thing, "__module__"):
            return "%s.%s" % (thing.__module__, thing.__name__)
    return repr(thing)
