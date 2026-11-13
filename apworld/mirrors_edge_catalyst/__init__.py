from worlds.LauncherComponents import Component, Type, components, launch

from .world import MECWorld as MECWorld


def run_client(*args: str) -> None:
    from .client.launch import launch_mec_client
    launch(launch_mec_client, name="Mirror's Edge Catalyst Client", args=args)


components.append(Component(
    "Mirror's Edge Catalyst Client",
    func=run_client,
    game_name="Mirror's Edge Catalyst",
    component_type=Type.CLIENT,
    supports_uri=True,
))
