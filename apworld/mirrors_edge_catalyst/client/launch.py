def launch_mec_client(*args: str) -> None:
    # imported lazily so generating a seed never loads the client or ctypes
    from .client import launch
    launch(*args)
