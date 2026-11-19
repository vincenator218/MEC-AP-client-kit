from worlds.LauncherComponents import Component, Type, components, launch

from .world import MECDashesWorld as MECDashesWorld


def run_client(*args: str) -> None:
    from .client.launch import launch_mecd_client
    launch(launch_mecd_client, name="Mirror's Edge Catalyst Dashes Client", args=args)


components.append(Component(
    "Mirror's Edge Catalyst Dashes Client",
    func=run_client,
    game_name="Mirror's Edge Catalyst Dashes",
    component_type=Type.CLIENT,
    supports_uri=True,
))
